import {
  BadRequestException,
  ConflictException,
  HttpException,
  Injectable,
  Logger,
  NotFoundException,
  UnprocessableEntityException,
} from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { createHash, randomUUID } from 'crypto';
import { extname } from 'path';
import { getErrorMessage } from '../../common/error-message';
import { MinioService } from '../../core/minio/minio.service';
import { PrismaService } from '../../core/prisma/prisma.service';
import { RagService } from '../rag/rag.service';
import { CreateKnowledgeDocumentDto } from './dto/create-knowledge-document.dto';
import { AppendDocumentSourceDto } from './dto/append-document-source.dto';
import { QueryKnowledgeDocumentsDto } from './dto/query-knowledge-documents.dto';
import { QueryTrashDocumentsDto } from './dto/query-trash-documents.dto';
import { UpdateDocumentCategoryDto } from './dto/update-document-category.dto';
import { UpdateDocumentTitleDto } from './dto/update-document-title.dto';
import { BatchMoveDocumentsDto } from './dto/batch-move-documents.dto';
import { BatchDeleteDocumentsDto } from './dto/batch-delete-documents.dto';
import { BatchRestoreDocumentsDto } from './dto/batch-restore-documents.dto';
import { BatchPurgeDocumentsDto } from './dto/batch-purge-documents.dto';
import { KnowledgeCategoriesService } from './knowledge-categories.service';
import {
  KnowledgeDocumentSummary,
  KnowledgeDocumentReplaceResponse,
  KnowledgeDocumentSource,
  KnowledgeDocumentSourceMutationResponse,
  KnowledgeDocumentUploadResponse,
  KnowledgeDocumentBatchMoveResponse,
  KnowledgeDocumentBatchDeleteResponse,
  KnowledgeDocumentBatchRestoreResponse,
  KnowledgeDocumentBatchPurgeResponse,
  TrashDocumentSummary,
  TrashListResponse,
  ProcessingTimings,
} from './knowledge-documents.types';

const MAX_FILE_SIZE = 50 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set([
  '.pdf',
  '.docx',
  '.txt',
  '.md',
  '.png',
  '.jpg',
  '.jpeg',
  '.webp',
  '.bmp',
  '.tif',
  '.tiff',
]);

type ExistingAttachment = Awaited<
  ReturnType<KnowledgeDocumentsService['findExistingByHash']>
>;

type SourceRow = {
  source_id: bigint;
  document_id: bigint;
  attachment_id: bigint;
  source_title: string;
  file_name: string;
  file_size: bigint | null;
  sort_order: number;
  is_primary: boolean;
  ingest_status: string;
  chunk_count: number;
  image_total: number;
  uploaded_at: Date;
  upload_timings: ProcessingTimings | null;
  ingest_timings: ProcessingTimings | null;
};

@Injectable()
export class KnowledgeDocumentsService {
  private readonly logger = new Logger(KnowledgeDocumentsService.name);
  private readonly replacementLocks = new Set<string>();

  constructor(
    private readonly prisma: PrismaService,
    private readonly storage: MinioService,
    private readonly rag: RagService,
    private readonly categories: KnowledgeCategoriesService,
  ) {}

  async listSources(
    docId: bigint,
  ): Promise<{ items: KnowledgeDocumentSource[] }> {
    const rows = await this.sourceRows(docId);
    return { items: rows.map((row) => this.toSource(row)) };
  }

  async appendSource(
    docId: bigint,
    file: Express.Multer.File,
    dto: AppendDocumentSourceDto,
  ): Promise<KnowledgeDocumentSourceMutationResponse> {
    return this.withDocumentLock(docId, async () => {
      const requestId = this.rag.createDocumentRequestId();
      const target = await this.requireSuccessfulDocument(docId);
      const prepared = this.prepareFile(file);
      const sourceTitle = dto.source_title?.trim() || prepared.filename;
      const duplicate = await this.findSourceByHash(prepared.hash);
      if (duplicate) {
        throw new ConflictException(
          duplicate.document_id === docId
            ? '该文件已经属于当前知识库文档'
            : '该文件已存在于其他知识库文档中',
        );
      }
      await this.assertHashNotSoftDeleted(prepared.hash);
      const timer = new UploadTimer();
      timer.record('validate_hash', '文件校验与 SHA-256', 0, 'success');
      await timer.measure('duplicate_check', '重复文件检查', () =>
        Promise.resolve(undefined),
      );
      const now = new Date();
      const objectKey = this.stagingObjectKey(
        docId,
        prepared.hash,
        prepared.filename,
        now,
      );
      const stored = await timer.measure('minio_upload', 'MinIO 原件上传', () =>
        this.storage.uploadFile(objectKey, file.buffer, {
          contentType: prepared.contentType,
        }),
      );
      let stagingDocId: bigint | null = null;
      let sourceId: bigint | null = null;
      let promotedSuccessfully = false;
      try {
        const staging = await timer.measure(
          'database_register',
          '数据库 staging 登记',
          () =>
            this.prisma.$transaction(async (tx) => {
              const attachment = await tx.sys_attachment.create({
                data: this.stagingAttachmentData({
                  docId,
                  prepared,
                  stored,
                  objectKey,
                  now,
                  remark: '公共知识库追加来源 staging',
                }),
              });
              const orders = await tx.$queryRaw<Array<{ next_order: number }>>(
                Prisma.sql`
                  SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order
                  FROM oa.kb_document_source
                  WHERE document_id = ${docId} AND deleted_at IS NULL
                `,
              );
              const sources = await tx.$queryRaw<
                Array<{ id: bigint }>
              >(Prisma.sql`
                INSERT INTO oa.kb_document_source (
                  document_id, attachment_id, source_title, sort_order,
                  is_primary, ingest_status, chunk_count, image_total,
                  image_kept, image_filtered, created_at, updated_at, status
                ) VALUES (
                  ${docId}, ${attachment.id}, ${sourceTitle},
                  ${Number(orders[0]?.next_order ?? 0)}, FALSE, 'pending',
                  0, 0, 0, 0, ${now}, ${now}, 'staging'
                ) RETURNING id
              `);
              const document = await tx.kb_document.create({
                data: this.stagingDocumentData(
                  target,
                  attachment.id,
                  now,
                  '追加来源',
                ),
              });
              return { document, sourceId: sources[0].id };
            }),
        );
        stagingDocId = staging.document.id;
        sourceId = staging.sourceId;
        const uploadTimings = timer.report('success');
        await this.persistUploadTimings(stagingDocId, uploadTimings);
        await this.persistSourceUploadTimings(sourceId, uploadTimings);
        const ingested = await this.rag.ingestDocument(
          stagingDocId.toString(),
          true,
          {
            routingDocId: docId.toString(),
            requestId,
          },
        );
        if (ingested.status !== 'success')
          throw new Error('staging ingest failed');
        const promoted = await this.rag.promoteSource({
          stagingDocId: stagingDocId.toString(),
          targetDocId: docId.toString(),
          sourceId: sourceId.toString(),
          mode: 'append',
          sourceTitle,
          requestId,
        });
        promotedSuccessfully = true;
        stagingDocId = null;
        const source = await this.getSource(sourceId, docId);
        return {
          document: await this.getSummary(docId),
          source,
          chunk_count: promoted.chunk_count,
          request_id: requestId,
        };
      } catch (error: unknown) {
        if (stagingDocId !== null) {
          await this.rag
            .cleanupStagingDocument(
              stagingDocId.toString(),
              docId.toString(),
              requestId,
            )
            .catch(() => undefined);
        } else if (!promotedSuccessfully) {
          await this.storage
            .deleteFile(objectKey, stored.bucket)
            .catch(() => undefined);
        }
        if (sourceId !== null && !promotedSuccessfully)
          await this.cancelSource(sourceId);
        this.rethrowSourceError(
          error,
          '后续文件处理失败，已有知识库内容未改变',
          requestId,
        );
      }
    });
  }

  async replaceSource(
    docId: bigint,
    sourceId: bigint,
    file: Express.Multer.File,
    dto: AppendDocumentSourceDto,
  ): Promise<KnowledgeDocumentSourceMutationResponse> {
    return this.withDocumentLock(docId, async () => {
      const requestId = this.rag.createDocumentRequestId();
      const target = await this.requireSuccessfulDocument(docId);
      const current = await this.getSourceRow(sourceId, docId);
      const prepared = this.prepareFile(file);
      const sourceTitle = dto.source_title?.trim() || prepared.filename;
      const duplicate = await this.findSourceByHash(prepared.hash);
      if (duplicate && duplicate.source_id !== sourceId) {
        throw new ConflictException('该文件已存在于知识库中');
      }
      if (
        duplicate?.source_id === sourceId &&
        current.source_title === sourceTitle
      ) {
        throw new ConflictException('文件与当前来源版本一致');
      }
      await this.assertHashNotSoftDeleted(prepared.hash);
      const timer = new UploadTimer();
      timer.record('validate_hash', '文件校验与 SHA-256', 0, 'success');
      const now = new Date();
      const objectKey = this.stagingObjectKey(
        docId,
        prepared.hash,
        prepared.filename,
        now,
      );
      const stored = await timer.measure('minio_upload', 'MinIO 原件上传', () =>
        this.storage.uploadFile(objectKey, file.buffer, {
          contentType: prepared.contentType,
        }),
      );
      let stagingDocId: bigint | null = null;
      let promotedSuccessfully = false;
      try {
        const staging = await timer.measure(
          'database_register',
          '数据库 staging 登记',
          () =>
            this.prisma.$transaction(async (tx) => {
              const attachment = await tx.sys_attachment.create({
                data: this.stagingAttachmentData({
                  docId,
                  prepared,
                  stored,
                  objectKey,
                  now,
                  remark: '公共知识库来源替换 staging',
                }),
              });
              return tx.kb_document.create({
                data: this.stagingDocumentData(
                  target,
                  attachment.id,
                  now,
                  '替换来源',
                ),
              });
            }),
        );
        stagingDocId = staging.id;
        const uploadTimings = timer.report('success');
        await this.persistUploadTimings(stagingDocId, uploadTimings);
        const ingested = await this.rag.ingestDocument(
          stagingDocId.toString(),
          true,
          {
            routingDocId: docId.toString(),
            requestId,
          },
        );
        if (ingested.status !== 'success')
          throw new Error('staging ingest failed');
        const promoted = await this.rag.promoteSource({
          stagingDocId: stagingDocId.toString(),
          targetDocId: docId.toString(),
          sourceId: sourceId.toString(),
          mode: 'replace',
          sourceTitle,
          requestId,
        });
        promotedSuccessfully = true;
        stagingDocId = null;
        return {
          document: await this.getSummary(docId),
          source: await this.getSource(sourceId, docId),
          chunk_count: promoted.chunk_count,
          request_id: requestId,
        };
      } catch (error: unknown) {
        if (stagingDocId !== null) {
          await this.rag
            .cleanupStagingDocument(
              stagingDocId.toString(),
              docId.toString(),
              requestId,
            )
            .catch(() => undefined);
        } else if (!promotedSuccessfully) {
          await this.storage
            .deleteFile(objectKey, stored.bucket)
            .catch(() => undefined);
        }
        this.rethrowSourceError(
          error,
          '源文件替换失败，原来源内容未改变',
          requestId,
        );
      }
    });
  }

  async rebuildSources(docId: bigint) {
    return this.withDocumentLock(docId, async () => {
      const requestId = this.rag.createDocumentRequestId();
      const target = await this.requireSuccessfulDocument(docId);
      const sourceRows = await this.sourceRows(docId);
      if (!sourceRows.length) {
        throw new ConflictException('该文档没有可重建的源文件');
      }
      const staging: Array<{ sourceId: bigint; stagingDocId: bigint }> = [];
      try {
        for (const source of sourceRows) {
          const now = new Date();
          const document = await this.prisma.kb_document.create({
            data: this.stagingDocumentData(
              target,
              source.attachment_id,
              now,
              `重建来源 ${source.source_id.toString()}`,
            ),
          });
          staging.push({
            sourceId: source.source_id,
            stagingDocId: document.id,
          });
          const result = await this.rag.ingestDocument(
            document.id.toString(),
            true,
            {
              routingDocId: docId.toString(),
              requestId,
            },
          );
          if (result.status !== 'success') {
            throw new Error('a source rebuild failed');
          }
        }
        return await this.rag.rebuildSources(
          docId.toString(),
          staging.map((item) => ({
            sourceId: item.sourceId.toString(),
            stagingDocId: item.stagingDocId.toString(),
          })),
          requestId,
        );
      } catch (error: unknown) {
        await Promise.all(
          staging.map((item) =>
            this.rag
              .cleanupStagingDocument(
                item.stagingDocId.toString(),
                docId.toString(),
                requestId,
              )
              .catch(() => undefined),
          ),
        );
        this.rethrowSourceError(
          error,
          '全部源文件重建失败，原知识库内容未改变',
          requestId,
        );
      }
    });
  }

  async replace(
    docId: bigint,
    file: Express.Multer.File,
    dto: CreateKnowledgeDocumentDto,
  ): Promise<KnowledgeDocumentReplaceResponse> {
    const lockKey = docId.toString();
    if (this.replacementLocks.has(lockKey)) {
      throw new ConflictException('该文档正在替换，请等待当前操作完成');
    }
    this.replacementLocks.add(lockKey);
    const requestId = this.rag.createDocumentRequestId();
    let stagingDocId: bigint | null = null;
    let uploadedObject: { bucket: string; objectKey: string } | null = null;
    try {
      const timer = new UploadTimer();
      let filename = '';
      let title = '';
      let hash = '';
      timer.measureSync('validate_hash', '文件校验与 SHA-256', () => {
        filename = normalizeFilename(file.originalname);
        validateKnowledgeFile(file.buffer, filename, file.mimetype);
        title = dto.title.trim();
        if (!title) throw new BadRequestException('文档标题不能为空');
        hash = createHash('sha256').update(file.buffer).digest('hex');
      });
      const category = await this.categories.requireAssignable(
        BigInt(dto.category_id),
      );

      const current = await this.prisma.kb_document.findFirst({
        where: { id: docId, deleted_at: null, status: 'active' },
        include: { sys_attachment: true },
      });
      if (!current?.sys_attachment) {
        throw new NotFoundException('知识库文档不存在');
      }
      if (current.embedding_status !== 'success') {
        throw new ConflictException('只有入库成功的文档可以替换文件');
      }
      const existing = await timer.measure(
        'duplicate_check',
        '重复文件检查',
        () => this.findExistingByHash(hash),
      );
      const existingDocId = existing?.kb_document[0]?.id;
      if (existingDocId !== undefined && existingDocId !== docId) {
        throw new ConflictException('该文件已存在于其他知识库文档中');
      }
      const metadataChanged =
        current.doc_title !== title || current.category_id !== category.id;
      if (existingDocId === docId && !metadataChanged) {
        throw new ConflictException('文件与当前版本一致');
      }
      await this.assertHashNotSoftDeleted(hash);

      const now = new Date();
      const extension = extname(filename).toLowerCase().slice(1);
      const safeName = sanitizeObjectFilename(filename);
      const objectKey = [
        'knowledge-base-staging',
        lockKey,
        String(now.getTime()),
        `${hash}_${randomUUID().replace(/-/g, '').slice(0, 8)}_${safeName}`,
      ].join('/');
      const contentType = canonicalMimeType(extname(filename).toLowerCase());
      const stored = await timer.measure('minio_upload', 'MinIO 原件上传', () =>
        this.storage.uploadFile(objectKey, file.buffer, { contentType }),
      );
      uploadedObject = { bucket: stored.bucket, objectKey };

      const staging = await timer.measure(
        'database_register',
        '数据库 staging 登记',
        () =>
          this.prisma.$transaction(async (tx) => {
            const attachment = await tx.sys_attachment.create({
              data: {
                biz_type: 'knowledge_base_staging',
                biz_id: docId,
                file_name: filename,
                file_ext: extension,
                mime_type: contentType,
                file_size: BigInt(stored.size),
                storage_type: 'minio',
                storage_path: objectKey,
                file_hash: hash,
                uploaded_by: null,
                uploaded_at: now,
                created_at: now,
                created_by: null,
                updated_at: now,
                updated_by: null,
                deleted_at: null,
                status: 'active',
                remark: `公共知识库替换 staging target=${lockKey}`,
                original_file_name: filename,
                current_file_name: objectKey.slice(
                  objectKey.lastIndexOf('/') + 1,
                ),
                file_exists_flag: '1',
                ai_index_status: 'pending',
                bucket: stored.bucket,
                object_key: objectKey,
                etag: stored.etag,
              },
            });
            const document = await tx.kb_document.create({
              data: {
                doc_title: title,
                doc_type: category.name,
                legal_category: category.name,
                category_id: category.id,
                attachment_id: attachment.id,
                content_text: null,
                embedding_status: 'pending',
                version_no: current.version_no,
                permission_level: current.permission_level,
                source_department_id: current.source_department_id,
                author_employee_id: current.author_employee_id,
                created_at: now,
                created_by: current.created_by,
                updated_at: now,
                updated_by: null,
                deleted_at: null,
                status: 'staging',
                remark: `等待替换文档 ${lockKey}`,
              },
            });
            return { attachment, document };
          }),
      );
      stagingDocId = staging.document.id;
      const uploadTimings = timer.report('success');
      await this.persistUploadTimings(stagingDocId, uploadTimings);

      const ingested = await this.rag.ingestDocument(
        stagingDocId.toString(),
        true,
        {
          routingDocId: docId.toString(),
          requestId,
        },
      );
      if (ingested.status !== 'success') {
        throw new Error('staging ingest failed');
      }
      const promoted = await this.rag.promoteDocument(
        stagingDocId.toString(),
        docId.toString(),
        requestId,
      );
      stagingDocId = null;
      uploadedObject = null;
      const summary = await this.getSummary(docId);
      return {
        document: summary,
        chunk_count: promoted.chunk_count,
        replaced: true,
        request_id: requestId,
      };
    } catch (error: unknown) {
      if (stagingDocId !== null) {
        await this.rag
          .cleanupStagingDocument(
            stagingDocId.toString(),
            docId.toString(),
            requestId,
          )
          .catch(() => undefined);
      } else if (uploadedObject) {
        await this.storage
          .deleteFile(uploadedObject.objectKey, uploadedObject.bucket)
          .catch(() => undefined);
      }
      if (error instanceof HttpException) {
        throw error;
      }
      this.logger.error(
        `知识库安全替换失败 doc_id=${lockKey}: ${getErrorMessage(error)}`,
      );
      throw new ConflictException({
        code: 'RAG_DOCUMENT_OPERATION_FAILED',
        message: '新文件处理失败，原知识库内容未改变',
        request_id: requestId,
      });
    } finally {
      this.replacementLocks.delete(lockKey);
    }
  }

  async create(
    file: Express.Multer.File,
    dto: CreateKnowledgeDocumentDto,
  ): Promise<KnowledgeDocumentUploadResponse> {
    const timer = new UploadTimer();
    let filename = '';
    let title = '';
    let hash = '';
    timer.measureSync('validate_hash', '文件校验与 SHA-256', () => {
      filename = normalizeFilename(file.originalname);
      validateKnowledgeFile(file.buffer, filename, file.mimetype);
      title = dto.title.trim();
      if (!title) throw new BadRequestException('文档标题不能为空');
      hash = createHash('sha256').update(file.buffer).digest('hex');
    });
    const category = await this.categories.requireAssignable(
      BigInt(dto.category_id),
    );

    const existing = await timer.measure(
      'duplicate_check',
      '重复文件检查',
      () => this.findExistingByHash(hash),
    );
    if (existing) return this.asUploadResponse(existing, true);
    const existingSource = await this.findSourceByHash(hash);
    if (existingSource) {
      return {
        document: await this.getSummary(existingSource.document_id),
        deduplicated: true,
      };
    }
    await this.assertHashNotSoftDeleted(hash);

    const now = new Date();
    const extension = extname(filename).toLowerCase().slice(1);
    const safeName = sanitizeObjectFilename(filename);
    const objectKey = [
      'knowledge-base',
      String(now.getUTCFullYear()),
      String(now.getUTCMonth() + 1).padStart(2, '0'),
      hash.slice(0, 2),
      `${hash}_${randomUUID().replace(/-/g, '').slice(0, 8)}_${safeName}`,
    ].join('/');
    const contentType = canonicalMimeType(extname(filename).toLowerCase());
    const stored = await timer.measure('minio_upload', 'MinIO 原件上传', () =>
      this.storage.uploadFile(objectKey, file.buffer, { contentType }),
    );

    try {
      const document = await timer.measure(
        'database_register',
        '数据库事务登记',
        () =>
          this.prisma.$transaction(async (tx) => {
            const attachment = await tx.sys_attachment.create({
              data: {
                biz_type: 'knowledge_base',
                biz_id: BigInt(0),
                file_name: filename,
                file_ext: extension,
                mime_type: contentType,
                file_size: BigInt(stored.size),
                storage_type: 'minio',
                storage_path: objectKey,
                file_hash: hash,
                uploaded_by: null,
                uploaded_at: now,
                created_at: now,
                created_by: null,
                updated_at: now,
                updated_by: null,
                deleted_at: null,
                status: 'active',
                remark: '公共知识库上传',
                original_file_name: filename,
                current_file_name: objectKey.slice(
                  objectKey.lastIndexOf('/') + 1,
                ),
                file_exists_flag: '1',
                ai_index_status: 'pending',
                bucket: stored.bucket,
                object_key: objectKey,
                etag: stored.etag,
              },
            });
            const created = await tx.kb_document.create({
              data: {
                doc_title: title,
                doc_type: category.name,
                legal_category: category.name,
                category_id: category.id,
                attachment_id: attachment.id,
                content_text: null,
                embedding_status: 'pending',
                version_no: 'v1',
                permission_level: 'public',
                created_at: now,
                created_by: null,
                updated_at: now,
                updated_by: null,
                deleted_at: null,
                status: 'active',
                remark: '公共知识库上传',
              },
            });
            await tx.$executeRaw(Prisma.sql`
              INSERT INTO oa.kb_document_source (
                document_id, attachment_id, source_title, sort_order,
                is_primary, ingest_status, chunk_count, image_total,
                image_kept, image_filtered, created_at, updated_at, status
              ) VALUES (
                ${created.id}, ${attachment.id}, ${filename}, 0, TRUE,
                'pending', 0, 0, 0, 0, ${now}, ${now}, 'active'
              )
            `);
            return { attachment, document: created };
          }),
      );
      const timings = timer.report('success');
      await this.persistUploadTimings(document.document.id, timings);
      return {
        document: await this.getSummary(document.document.id),
        deduplicated: false,
      };
    } catch (error: unknown) {
      await this.storage
        .deleteFile(objectKey, stored.bucket)
        .catch((cleanupError) => {
          this.logger.error(
            `补偿删除公共知识库对象失败 ${objectKey}: ${getErrorMessage(cleanupError)}`,
          );
        });
      if (
        error instanceof Prisma.PrismaClientKnownRequestError &&
        error.code === 'P2002'
      ) {
        const winner = await this.findExistingByHash(hash);
        if (winner) return this.asUploadResponse(winner, true);
      }
      throw error;
    }
  }

  async list(query: QueryKnowledgeDocumentsDto) {
    // kb_document 是知识库归属的权威记录；早期种子数据的附件 biz_type 为 document，
    // 不能用附件类型过滤，否则分类计数会包含文档而管理列表看不到它们。
    const conditions: Prisma.Sql[] = [
      Prisma.sql`d.deleted_at IS NULL`,
      Prisma.sql`d.status = 'active'`,
      Prisma.sql`a.deleted_at IS NULL`,
    ];
    if (query.category_id) {
      const categoryId = BigInt(query.category_id);
      conditions.push(Prisma.sql`
        d.category_id IN (
          WITH RECURSIVE descendants AS (
            SELECT id FROM oa.kb_category
            WHERE id = ${categoryId} AND deleted_at IS NULL AND status = 'active'
            UNION ALL
            SELECT child.id FROM oa.kb_category child
            JOIN descendants parent ON child.parent_id = parent.id
            WHERE child.deleted_at IS NULL AND child.status = 'active'
          )
          SELECT id FROM descendants
        )
      `);
    }
    if (query.status)
      conditions.push(Prisma.sql`d.embedding_status = ${query.status}`);
    const keyword = query.keyword?.trim();
    if (keyword)
      conditions.push(Prisma.sql`d.doc_title ILIKE ${`%${keyword}%`}`);
    const where = Prisma.join(conditions, ' AND ');
    const offset = (query.page - 1) * query.page_size;

    type Row = {
      doc_id: bigint;
      attachment_id: bigint;
      title: string;
      category: string | null;
      category_id: bigint;
      category_name: string;
      category_path: string[];
      category_path_ids: bigint[];
      category_sensitive: boolean;
      embedding_status: string;
      file_name: string;
      file_size: bigint | null;
      image_total: number | null;
      created_at: Date;
      last_uploaded_at: Date;
      upload_timings: ProcessingTimings | null;
      ingest_timings: ProcessingTimings | null;
      source_count: bigint;
    };
    const [rows, counts] = await Promise.all([
      this.prisma.$queryRaw<Row[]>(Prisma.sql`
        WITH RECURSIVE category_paths AS (
          SELECT c.id, c.parent_id, ARRAY[c.category_name]::text[] AS path,
                 ARRAY[c.id]::bigint[] AS path_ids, c.sensitive AS effective_sensitive
          FROM oa.kb_category c
          WHERE c.parent_id IS NULL AND c.deleted_at IS NULL
          UNION ALL
          SELECT child.id, child.parent_id, parent.path || child.category_name,
                 parent.path_ids || child.id,
                 parent.effective_sensitive OR child.sensitive
          FROM oa.kb_category child
          JOIN category_paths parent ON child.parent_id = parent.id
          WHERE child.deleted_at IS NULL
        )
        SELECT d.id AS doc_id, a.id AS attachment_id, d.doc_title AS title,
               array_to_string(cp.path, ' / ') AS category,
               d.category_id, c.category_name, cp.path AS category_path,
               cp.path_ids AS category_path_ids,
               cp.effective_sensitive AS category_sensitive,
               d.embedding_status,
               COALESCE(a.original_file_name, a.file_name) AS file_name,
               a.file_size, COALESCE(d.image_total, 0) AS image_total, d.created_at,
               COALESCE((SELECT MAX(COALESCE(
                  (s.upload_timings->>'completed_at')::timestamptz,
                  s.created_at
                ))
                FROM oa.kb_document_source s
                WHERE s.document_id = d.id AND s.deleted_at IS NULL
                  AND s.status = 'active'), d.created_at) AS last_uploaded_at,
               d.upload_timings, d.ingest_timings,
               (SELECT COUNT(*) FROM oa.kb_document_source s
                WHERE s.document_id = d.id AND s.deleted_at IS NULL
                  AND s.status = 'active')::bigint AS source_count
        FROM oa.kb_document d
        JOIN oa.sys_attachment a ON a.id = d.attachment_id
        JOIN oa.kb_category c ON c.id = d.category_id
        JOIN category_paths cp ON cp.id = d.category_id
        WHERE ${where}
        ORDER BY d.created_at DESC, d.id DESC
        LIMIT ${query.page_size} OFFSET ${offset}
      `),
      this.prisma.$queryRaw<{ total: bigint }[]>(Prisma.sql`
        SELECT COUNT(*)::bigint AS total
        FROM oa.kb_document d
        JOIN oa.sys_attachment a ON a.id = d.attachment_id
        WHERE ${where}
      `),
    ]);
    return {
      items: rows.map(
        (row) =>
          ({
            doc_id: row.doc_id.toString(),
            attachment_id: row.attachment_id.toString(),
            title: row.title,
            category: row.category ?? row.category_name,
            category_id: row.category_id.toString(),
            category_name: row.category_name,
            category_path: row.category_path,
            category_path_ids: row.category_path_ids.map(String),
            category_sensitive: row.category_sensitive,
            embedding_status: row.embedding_status,
            file_name: row.file_name,
            file_size: row.file_size?.toString() ?? null,
            image_total: Number(row.image_total ?? 0),
            created_at: row.created_at.toISOString(),
            last_uploaded_at: row.last_uploaded_at.toISOString(),
            upload_timings: row.upload_timings,
            ingest_timings: row.ingest_timings,
            source_count: Number(row.source_count),
          }) satisfies KnowledgeDocumentSummary,
      ),
      total: Number(counts[0]?.total ?? 0),
      page: query.page,
      page_size: query.page_size,
    };
  }

  async updateCategory(
    docId: bigint,
    dto: UpdateDocumentCategoryDto,
  ): Promise<KnowledgeDocumentSummary> {
    await this.assertActiveDocument(docId);
    const category = await this.categories.requireAssignable(
      BigInt(dto.category_id),
    );
    await this.prisma.$executeRaw(Prisma.sql`
      UPDATE oa.kb_document
      SET category_id = ${category.id}, legal_category = ${category.name},
          updated_at = NOW()
      WHERE id = ${docId} AND deleted_at IS NULL AND status = 'active'
    `);
    return this.getSummary(docId);
  }

  async updateTitle(
    docId: bigint,
    dto: UpdateDocumentTitleDto,
  ): Promise<KnowledgeDocumentSummary> {
    await this.assertActiveDocument(docId);
    await this.prisma.$executeRaw(Prisma.sql`
      UPDATE oa.kb_document
      SET doc_title = ${dto.title.trim()}, updated_at = NOW()
      WHERE id = ${docId} AND deleted_at IS NULL AND status = 'active'
    `);
    return this.getSummary(docId);
  }

  async batchMove(
    dto: BatchMoveDocumentsDto,
  ): Promise<KnowledgeDocumentBatchMoveResponse> {
    const idSet = new Set(dto.doc_ids);
    const ids = [...idSet].map((id) => BigInt(id));
    const category = await this.categories.requireAssignable(
      BigInt(dto.category_id),
    );
    await this.requireActiveDocuments(ids);
    const result = await this.prisma.$executeRaw<number>(Prisma.sql`
      UPDATE oa.kb_document
      SET category_id = ${category.id},
          legal_category = ${category.name},
          updated_at = NOW()
      WHERE id IN (${Prisma.join(ids)})
        AND deleted_at IS NULL
        AND status = 'active'
    `);
    return {
      moved: Number(result),
      category_id: category.id.toString(),
      category_path: category.path,
    };
  }

  async batchDelete(
    dto: BatchDeleteDocumentsDto,
  ): Promise<KnowledgeDocumentBatchDeleteResponse> {
    const idSet = new Set(dto.doc_ids);
    const ids = [...idSet].map((id) => BigInt(id));
    await this.requireActiveDocuments(ids);

    const attachments = await this.prisma.$queryRaw<
      Array<{ id: bigint; bucket: string | null; object_key: string | null }>
    >(Prisma.sql`
      SELECT DISTINCT a.id, a.bucket, a.object_key
      FROM oa.sys_attachment a
      WHERE a.deleted_at IS NULL
        AND a.status = 'active'
        AND (
          a.id IN (
            SELECT d.attachment_id FROM oa.kb_document d
            WHERE d.id IN (${Prisma.join(ids)}) AND d.deleted_at IS NULL AND d.status = 'active'
          )
          OR a.id IN (
            SELECT s.attachment_id FROM oa.kb_document_source s
            WHERE s.document_id IN (${Prisma.join(ids)}) AND s.deleted_at IS NULL AND s.status = 'active'
          )
        )
    `);

    return this.withDocumentLocks(ids, async () => {
      const now = new Date();
      await this.prisma.$transaction(async (tx) => {
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.kb_document
          SET status = 'deleted', deleted_at = ${now}, updated_at = ${now}
          WHERE id IN (${Prisma.join(ids)})
            AND deleted_at IS NULL
            AND status = 'active'
        `);
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.kb_document_source
          SET status = 'deleted', deleted_at = ${now}, updated_at = ${now}
          WHERE document_id IN (${Prisma.join(ids)})
            AND deleted_at IS NULL
            AND status = 'active'
        `);
        if (attachments.length > 0) {
          const attachmentIds = attachments.map((a) => a.id);
          await tx.$executeRaw(Prisma.sql`
            UPDATE oa.sys_attachment
            SET status = 'soft_deleted', deleted_at = ${now}, updated_at = ${now}
            WHERE id IN (${Prisma.join(attachmentIds)})
              AND deleted_at IS NULL
              AND status = 'active'
          `);
        }
      });

      // 纯软删除：保留原件、派生图片与 Milvus 向量，不访问对象存储或 RAG 服务。
      // 文档可经"回收站"恢复或永久删除。检索授权门已按 status='active' AND deleted_at IS NULL
      // 过滤，软删文档对 /search、/chat 不可见。
      return {
        deleted: ids.length,
        mode: 'soft' as const,
        artifacts_retained: true as const,
      };
    });
  }

  async listTrash(query: QueryTrashDocumentsDto): Promise<TrashListResponse> {
    const conditions: Prisma.Sql[] = [
      Prisma.sql`d.deleted_at IS NOT NULL`,
      Prisma.sql`d.status = 'deleted'`,
    ];
    if (query.category_id) {
      const categoryId = BigInt(query.category_id);
      // 回收站筛选需兼容已停用的原分类，故后代 CTE 不过滤 status='active'。
      conditions.push(Prisma.sql`
        d.category_id IN (
          WITH RECURSIVE descendants AS (
            SELECT id FROM oa.kb_category
            WHERE id = ${categoryId} AND deleted_at IS NULL
            UNION ALL
            SELECT child.id FROM oa.kb_category child
            JOIN descendants parent ON child.parent_id = parent.id
            WHERE child.deleted_at IS NULL
          )
          SELECT id FROM descendants
        )
      `);
    }
    const keyword = query.keyword?.trim();
    if (keyword)
      conditions.push(Prisma.sql`d.doc_title ILIKE ${`%${keyword}%`}`);
    const where = Prisma.join(conditions, ' AND ');
    const offset = (query.page - 1) * query.page_size;
    const orderBy =
      query.sort === 'title'
        ? query.order === 'asc'
          ? Prisma.sql`ORDER BY d.doc_title ASC, d.id DESC`
          : Prisma.sql`ORDER BY d.doc_title DESC, d.id DESC`
        : query.order === 'asc'
          ? Prisma.sql`ORDER BY d.deleted_at ASC, d.id DESC`
          : Prisma.sql`ORDER BY d.deleted_at DESC, d.id DESC`;

    type Row = {
      doc_id: bigint;
      attachment_id: bigint | null;
      title: string;
      category_id: bigint | null;
      category_name: string | null;
      category_path: string[] | null;
      category_path_ids: bigint[] | null;
      category_valid: boolean;
      deleted_at: Date;
      embedding_status: string;
      file_name: string | null;
      file_size: bigint | null;
      source_count: bigint;
    };
    const [rows, counts] = await Promise.all([
      this.prisma.$queryRaw<Row[]>(Prisma.sql`
        WITH RECURSIVE category_paths AS (
          SELECT c.id, c.parent_id, ARRAY[c.category_name]::text[] AS path,
                 ARRAY[c.id]::bigint[] AS path_ids
          FROM oa.kb_category c
          WHERE c.parent_id IS NULL AND c.deleted_at IS NULL
          UNION ALL
          SELECT child.id, child.parent_id, parent.path || child.category_name,
                 parent.path_ids || child.id
          FROM oa.kb_category child
          JOIN category_paths parent ON child.parent_id = parent.id
          WHERE child.deleted_at IS NULL
        )
        SELECT d.id AS doc_id, a.id AS attachment_id, d.doc_title AS title,
               d.category_id, c.category_name,
               cp.path AS category_path, cp.path_ids AS category_path_ids,
               (c.id IS NOT NULL AND c.status = 'active' AND c.assignable IS TRUE) AS category_valid,
               d.deleted_at, d.embedding_status,
               COALESCE(a.original_file_name, a.file_name) AS file_name,
               a.file_size,
               (SELECT COUNT(*) FROM oa.kb_document_source s
                WHERE s.document_id = d.id) AS source_count
        FROM oa.kb_document d
        LEFT JOIN oa.sys_attachment a ON a.id = d.attachment_id
        LEFT JOIN oa.kb_category c ON c.id = d.category_id
        LEFT JOIN category_paths cp ON cp.id = d.category_id
        WHERE ${where}
        ${orderBy}
        LIMIT ${query.page_size} OFFSET ${offset}
      `),
      this.prisma.$queryRaw<{ total: bigint }[]>(Prisma.sql`
        SELECT COUNT(*)::bigint AS total
        FROM oa.kb_document d
        WHERE ${where}
      `),
    ]);
    return {
      items: rows.map((row) => {
        const categoryValid = Boolean(row.category_valid);
        return {
          doc_id: row.doc_id.toString(),
          attachment_id: row.attachment_id?.toString() ?? '',
          title: row.title,
          category_id: row.category_id?.toString() ?? null,
          category_name: row.category_name ?? null,
          category_path: row.category_path ?? null,
          category_path_ids: row.category_path_ids?.map(String) ?? null,
          category_valid: categoryValid,
          restorable: categoryValid,
          deleted_at: row.deleted_at.toISOString(),
          embedding_status: row.embedding_status,
          file_name: row.file_name ?? '',
          file_size: row.file_size?.toString() ?? null,
          source_count: Number(row.source_count),
        } satisfies TrashDocumentSummary;
      }),
      total: Number(counts[0]?.total ?? 0),
      page: query.page,
      page_size: query.page_size,
    };
  }

  async batchRestore(
    dto: BatchRestoreDocumentsDto,
  ): Promise<KnowledgeDocumentBatchRestoreResponse> {
    const idSet = new Set(dto.doc_ids);
    const ids = [...idSet].map((id) => BigInt(id));
    await this.requireDeletedDocuments(ids);

    // 1) 解析每个文档的原分类是否仍可归档；失效的必须在 category_overrides 中给出新分类。
    const overrides = dto.category_overrides ?? {};
    const docRows = await this.prisma.$queryRaw<
      Array<{ id: bigint; category_valid: boolean }>
    >(Prisma.sql`
      SELECT d.id,
             (c.id IS NOT NULL AND c.status = 'active' AND c.assignable IS TRUE) AS category_valid
      FROM oa.kb_document d
      LEFT JOIN oa.kb_category c ON c.id = d.category_id
      WHERE d.id IN (${Prisma.join(ids)}) AND d.status = 'deleted'
    `);
    const newCategoryByDoc = new Map<bigint, { id: bigint; name: string }>();
    for (const row of docRows) {
      if (row.category_valid) continue; // 原分类有效，保持不变
      const override = overrides[row.id.toString()];
      if (!override) {
        throw new UnprocessableEntityException({
          code: 'RESTORE_CATEGORY_INVALID',
          message: `文档 ${row.id} 的原分类已失效，需指定新的可归档分类`,
          doc_id: row.id.toString(),
        });
      }
      const cat = await this.categories.requireAssignable(BigInt(override));
      newCategoryByDoc.set(row.id, { id: cat.id, name: cat.name });
    }

    // 2) 校验原件仍存在于 MinIO（任一缺失则不写库）。
    const originals = await this.prisma.$queryRaw<
      Array<{ id: bigint; bucket: string | null; object_key: string | null }>
    >(Prisma.sql`
      SELECT DISTINCT a.id, a.bucket, a.object_key
      FROM oa.sys_attachment a
      WHERE a.status = 'soft_deleted' AND a.deleted_at IS NOT NULL
        AND (
          a.id IN (
            SELECT d.attachment_id FROM oa.kb_document d
            WHERE d.id IN (${Prisma.join(ids)}) AND d.attachment_id IS NOT NULL
          )
          OR a.id IN (
            SELECT s.attachment_id FROM oa.kb_document_source s
            WHERE s.document_id IN (${Prisma.join(ids)}) AND s.attachment_id IS NOT NULL
          )
        )
    `);
    for (const a of originals) {
      const exists = await this.storage.fileExists(
        a.object_key ?? '',
        a.bucket ?? undefined,
      );
      if (!exists) {
        throw new UnprocessableEntityException({
          code: 'RESTORE_ORIGINAL_MISSING',
          message: '部分原件已丢失，无法恢复，请改用永久删除',
          object_key: a.object_key,
        });
      }
    }

    // 3) 校验 RAG 侧派生产物（Milvus chunks + 派生图片）齐全。
    const verify = await this.rag.verifyRestoreDocuments(ids.map(String));
    const failed = verify.items.filter((item) => !item.ok);
    if (failed.length > 0) {
      throw new UnprocessableEntityException({
        code: 'RESTORE_ARTIFACTS_MISSING',
        message: '部分文档的向量或派生图片已丢失，无法恢复，请改用永久删除',
        details: failed,
      });
    }

    // 4) 单事务原子恢复：不重新解析或生成向量。
    const attachmentIds = originals.map((a) => a.id);
    await this.prisma.$transaction(async (tx) => {
      await tx.$executeRaw(Prisma.sql`
        UPDATE oa.kb_document
        SET status = 'active', deleted_at = NULL, updated_at = NOW()
        WHERE id IN (${Prisma.join(ids)}) AND status = 'deleted'
      `);
      await tx.$executeRaw(Prisma.sql`
        UPDATE oa.kb_document_source
        SET status = 'active', deleted_at = NULL, updated_at = NOW()
        WHERE document_id IN (${Prisma.join(ids)}) AND status = 'deleted'
      `);
      if (attachmentIds.length > 0) {
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.sys_attachment
          SET status = 'active', deleted_at = NULL, updated_at = NOW()
          WHERE id IN (${Prisma.join(attachmentIds)}) AND status = 'soft_deleted'
        `);
      }
      for (const [docId, cat] of newCategoryByDoc) {
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.kb_document
          SET category_id = ${cat.id}, legal_category = ${cat.name}, updated_at = NOW()
          WHERE id = ${docId}
        `);
      }
    });

    return {
      restored: ids.length,
      doc_ids: ids.map(String),
      request_id: verify.request_id,
    };
  }

  async batchPurge(
    dto: BatchPurgeDocumentsDto,
  ): Promise<KnowledgeDocumentBatchPurgeResponse> {
    const idSet = new Set(dto.doc_ids);
    const ids = [...idSet].map((id) => BigInt(id));
    const rows = await this.prisma.$queryRaw<
      Array<{ id: bigint; status: string }>
    >(Prisma.sql`
      SELECT id, status FROM oa.kb_document WHERE id IN (${Prisma.join(ids)})
    `);
    const foundIds = new Set(rows.map((r) => r.id.toString()));
    for (const id of ids) {
      if (!foundIds.has(id.toString())) {
        throw new NotFoundException('部分知识库文档不存在');
      }
    }
    const toPurge = rows.filter((r) => r.status === 'deleted');
    const alreadyPurged = rows.filter((r) => r.status === 'purged');
    const invalid = rows.filter(
      (r) => r.status !== 'deleted' && r.status !== 'purged',
    );
    if (invalid.length > 0) {
      throw new NotFoundException('部分文档不在回收站中，无法永久删除');
    }
    if (toPurge.length === 0) {
      return { purged: 0, already_purged: alreadyPurged.length };
    }
    const toPurgeIds = toPurge.map((r) => r.id);

    // 收集原件对象键（best-effort 删除，失败仅告警，不影响后续）。
    const originals = await this.prisma.$queryRaw<
      Array<{ id: bigint; bucket: string | null; object_key: string | null }>
    >(Prisma.sql`
      SELECT DISTINCT a.id, a.bucket, a.object_key
      FROM oa.sys_attachment a
      WHERE a.deleted_at IS NOT NULL
        AND a.status = 'soft_deleted'
        AND (
          a.id IN (
            SELECT d.attachment_id FROM oa.kb_document d
            WHERE d.id IN (${Prisma.join(toPurgeIds)}) AND d.attachment_id IS NOT NULL
          )
          OR a.id IN (
            SELECT s.attachment_id FROM oa.kb_document_source s
            WHERE s.document_id IN (${Prisma.join(toPurgeIds)}) AND s.attachment_id IS NOT NULL
          )
        )
    `);
    for (const a of originals) {
      await this.storage
        .deleteFile(a.object_key ?? '', a.bucket ?? undefined)
        .catch((error: unknown) => {
          this.logger.warn(
            `永久删除附件 MinIO 对象失败: ${a.object_key}: ${getErrorMessage(error)}`,
          );
        });
    }

    // RAG 侧清理 Milvus chunks + kb_document_image 行 + 派生图片对象（幂等）。
    // 抛错则不标记 purged，文档留在回收站可重试。
    const requestId = await this.rag.batchDeleteDocuments(
      toPurgeIds.map((id) => id.toString()),
    );

    const attachmentIds = originals.map((a) => a.id);
    await this.prisma.$transaction(async (tx) => {
      await tx.$executeRaw(Prisma.sql`
        UPDATE oa.kb_document
        SET status = 'purged', updated_at = NOW()
        WHERE id IN (${Prisma.join(toPurgeIds)}) AND status = 'deleted'
      `);
      await tx.$executeRaw(Prisma.sql`
        UPDATE oa.kb_document_source
        SET status = 'purged', updated_at = NOW()
        WHERE document_id IN (${Prisma.join(toPurgeIds)}) AND status = 'deleted'
      `);
      if (attachmentIds.length > 0) {
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.sys_attachment
          SET status = 'purged', updated_at = NOW()
          WHERE id IN (${Prisma.join(attachmentIds)}) AND status = 'soft_deleted'
        `);
      }
    });

    return {
      purged: toPurgeIds.length,
      already_purged: alreadyPurged.length,
      request_id: requestId,
    };
  }

  private async requireActiveDocuments(ids: bigint[]): Promise<void> {
    if (ids.length === 0) return;
    const rows = await this.prisma.$queryRaw<Array<{ id: bigint }>>(
      Prisma.sql`
        SELECT id FROM oa.kb_document
        WHERE id IN (${Prisma.join(ids)})
          AND deleted_at IS NULL
          AND status = 'active'
      `,
    );
    if (rows.length !== ids.length) {
      throw new NotFoundException('部分知识库文档不存在或已删除');
    }
  }

  private async requireDeletedDocuments(ids: bigint[]): Promise<void> {
    if (ids.length === 0) return;
    const rows = await this.prisma.$queryRaw<Array<{ id: bigint }>>(
      Prisma.sql`
        SELECT id FROM oa.kb_document
        WHERE id IN (${Prisma.join(ids)})
          AND deleted_at IS NOT NULL
          AND status = 'deleted'
      `,
    );
    if (rows.length !== ids.length) {
      throw new NotFoundException('部分文档不在回收站中或状态已改变');
    }
  }

  async assertActiveDocument(docId: bigint): Promise<void> {
    const document = await this.prisma.kb_document.findFirst({
      where: { id: docId, deleted_at: null, status: 'active' },
      select: { id: true },
    });
    if (!document) throw new NotFoundException('知识库文档不存在');
  }

  private async withDocumentLocks<T>(
    docIds: bigint[],
    operation: () => Promise<T>,
  ): Promise<T> {
    const keys = docIds.map((id) => id.toString());
    for (const key of keys) {
      if (this.replacementLocks.has(key)) {
        throw new ConflictException('部分文档正在执行追加、替换或重建');
      }
    }
    for (const key of keys) {
      this.replacementLocks.add(key);
    }
    try {
      return await operation();
    } finally {
      for (const key of keys) {
        this.replacementLocks.delete(key);
      }
    }
  }

  private async withDocumentLock<T>(
    docId: bigint,
    operation: () => Promise<T>,
  ): Promise<T> {
    const key = docId.toString();
    if (this.replacementLocks.has(key)) {
      throw new ConflictException('该文档正在执行追加、替换或重建');
    }
    this.replacementLocks.add(key);
    try {
      return await operation();
    } finally {
      this.replacementLocks.delete(key);
    }
  }

  private async requireSuccessfulDocument(docId: bigint) {
    const document = await this.prisma.kb_document.findFirst({
      where: { id: docId, deleted_at: null, status: 'active' },
    });
    if (!document) throw new NotFoundException('知识库文档不存在');
    if (document.embedding_status !== 'success') {
      throw new ConflictException('只有入库成功的文档可以追加或替换来源');
    }
    return document;
  }

  private prepareFile(file: Express.Multer.File): {
    filename: string;
    hash: string;
    extension: string;
    contentType: string;
  } {
    const filename = normalizeFilename(file.originalname);
    validateKnowledgeFile(file.buffer, filename, file.mimetype);
    return {
      filename,
      hash: createHash('sha256').update(file.buffer).digest('hex'),
      extension: extname(filename).toLowerCase().slice(1),
      contentType: canonicalMimeType(extname(filename).toLowerCase()),
    };
  }

  private stagingObjectKey(
    docId: bigint,
    hash: string,
    filename: string,
    now: Date,
  ): string {
    return [
      'knowledge-base-staging',
      docId.toString(),
      String(now.getTime()),
      `${hash}_${randomUUID().replace(/-/g, '').slice(0, 8)}_${sanitizeObjectFilename(filename)}`,
    ].join('/');
  }

  private stagingAttachmentData(input: {
    docId: bigint;
    prepared: {
      filename: string;
      hash: string;
      extension: string;
      contentType: string;
    };
    stored: { bucket: string; etag: string; size: number };
    objectKey: string;
    now: Date;
    remark: string;
  }): Prisma.sys_attachmentUncheckedCreateInput {
    return {
      biz_type: 'knowledge_base_staging',
      biz_id: input.docId,
      file_name: input.prepared.filename,
      file_ext: input.prepared.extension,
      mime_type: input.prepared.contentType,
      file_size: BigInt(input.stored.size),
      storage_type: 'minio',
      storage_path: input.objectKey,
      file_hash: input.prepared.hash,
      uploaded_by: null,
      uploaded_at: input.now,
      created_at: input.now,
      created_by: null,
      updated_at: input.now,
      updated_by: null,
      deleted_at: null,
      status: 'active',
      remark: input.remark,
      original_file_name: input.prepared.filename,
      current_file_name: input.objectKey.slice(
        input.objectKey.lastIndexOf('/') + 1,
      ),
      file_exists_flag: '1',
      ai_index_status: 'pending',
      bucket: input.stored.bucket,
      object_key: input.objectKey,
      etag: input.stored.etag,
    };
  }

  private stagingDocumentData(
    target: {
      doc_title: string;
      doc_type: string;
      legal_category: string | null;
      category_id: bigint;
      version_no: string;
      permission_level: string;
      source_department_id: bigint | null;
      author_employee_id: bigint | null;
      created_by: bigint | null;
    },
    attachmentId: bigint,
    now: Date,
    action: string,
  ): Prisma.kb_documentUncheckedCreateInput {
    return {
      doc_title: target.doc_title,
      doc_type: target.doc_type,
      legal_category: target.legal_category,
      category_id: target.category_id,
      attachment_id: attachmentId,
      content_text: null,
      embedding_status: 'pending',
      version_no: target.version_no,
      permission_level: target.permission_level,
      source_department_id: target.source_department_id,
      author_employee_id: target.author_employee_id,
      created_at: now,
      created_by: target.created_by,
      updated_at: now,
      updated_by: null,
      deleted_at: null,
      status: 'staging',
      remark: `${action} staging`,
    };
  }

  private async sourceRows(docId: bigint): Promise<SourceRow[]> {
    return this.prisma.$queryRaw<SourceRow[]>(Prisma.sql`
      SELECT s.id AS source_id, s.document_id, s.attachment_id,
             s.source_title, COALESCE(a.original_file_name, a.file_name) AS file_name,
             a.file_size, s.sort_order, s.is_primary, s.ingest_status,
             s.chunk_count, s.image_total,
             COALESCE((s.upload_timings->>'completed_at')::timestamptz, s.created_at) AS uploaded_at,
             s.upload_timings, s.ingest_timings
      FROM oa.kb_document_source s
      JOIN oa.sys_attachment a ON a.id = s.attachment_id
      WHERE s.document_id = ${docId} AND s.deleted_at IS NULL
        AND s.status = 'active' AND a.deleted_at IS NULL
      ORDER BY s.sort_order, s.id
    `);
  }

  private async getSourceRow(
    sourceId: bigint,
    docId: bigint,
  ): Promise<SourceRow> {
    const rows = await this.prisma.$queryRaw<SourceRow[]>(Prisma.sql`
      SELECT s.id AS source_id, s.document_id, s.attachment_id,
             s.source_title, COALESCE(a.original_file_name, a.file_name) AS file_name,
             a.file_size, s.sort_order, s.is_primary, s.ingest_status,
             s.chunk_count, s.image_total,
             COALESCE((s.upload_timings->>'completed_at')::timestamptz, s.created_at) AS uploaded_at,
             s.upload_timings, s.ingest_timings
      FROM oa.kb_document_source s
      JOIN oa.sys_attachment a ON a.id = s.attachment_id
      WHERE s.id = ${sourceId} AND s.document_id = ${docId}
        AND s.deleted_at IS NULL AND s.status = 'active'
      LIMIT 1
    `);
    if (!rows[0]) throw new NotFoundException('知识库源文件不存在');
    return rows[0];
  }

  private async getSource(
    sourceId: bigint,
    docId: bigint,
  ): Promise<KnowledgeDocumentSource> {
    return this.toSource(await this.getSourceRow(sourceId, docId));
  }

  private toSource(row: SourceRow): KnowledgeDocumentSource {
    return {
      source_id: row.source_id.toString(),
      document_id: row.document_id.toString(),
      attachment_id: row.attachment_id.toString(),
      source_title: row.source_title,
      file_name: row.file_name,
      file_size: row.file_size?.toString() ?? null,
      sort_order: Number(row.sort_order),
      is_primary: Boolean(row.is_primary),
      ingest_status: row.ingest_status,
      chunk_count: Number(row.chunk_count),
      image_total: Number(row.image_total),
      uploaded_at: row.uploaded_at.toISOString(),
      upload_timings: row.upload_timings,
      ingest_timings: row.ingest_timings,
    };
  }

  private async findSourceByHash(hash: string): Promise<{
    source_id: bigint;
    document_id: bigint;
  } | null> {
    const rows = await this.prisma.$queryRaw<
      Array<{ source_id: bigint; document_id: bigint }>
    >(Prisma.sql`
      SELECT s.id AS source_id, s.document_id
      FROM oa.kb_document_source s
      JOIN oa.sys_attachment a ON a.id = s.attachment_id
      WHERE a.file_hash = ${hash} AND a.deleted_at IS NULL
        AND a.status = 'active' AND s.deleted_at IS NULL
        AND s.status = 'active'
      LIMIT 1
    `);
    return rows[0] ?? null;
  }

  private async persistSourceUploadTimings(
    sourceId: bigint,
    timings: ProcessingTimings,
  ): Promise<void> {
    await this.prisma.$executeRaw(Prisma.sql`
      UPDATE oa.kb_document_source
      SET upload_timings = CAST(${JSON.stringify(timings)} AS jsonb),
          updated_at = NOW()
      WHERE id = ${sourceId}
    `);
  }

  private async cancelSource(sourceId: bigint): Promise<void> {
    await this.prisma
      .$executeRaw(
        Prisma.sql`
      UPDATE oa.kb_document_source
      SET status = 'cancelled', deleted_at = NOW(), updated_at = NOW()
      WHERE id = ${sourceId} AND status = 'staging'
    `,
      )
      .catch(() => undefined);
  }

  private rethrowSourceError(
    error: unknown,
    message: string,
    requestId: string,
  ): never {
    if (error instanceof HttpException) {
      throw error;
    }
    this.logger.error(`${message}: ${getErrorMessage(error)}`);
    throw new ConflictException({
      code: 'RAG_DOCUMENT_OPERATION_FAILED',
      message,
      request_id: requestId,
    });
  }

  private async getSummary(docId: bigint): Promise<KnowledgeDocumentSummary> {
    type Row = {
      doc_id: bigint;
      attachment_id: bigint;
      title: string;
      category: string | null;
      category_id: bigint;
      category_name: string;
      category_path: string[];
      category_path_ids: bigint[];
      category_sensitive: boolean;
      embedding_status: string;
      file_name: string;
      file_size: bigint | null;
      image_total: number | null;
      created_at: Date;
      last_uploaded_at: Date;
      upload_timings: ProcessingTimings | null;
      ingest_timings: ProcessingTimings | null;
      source_count: bigint;
    };
    const rows = await this.prisma.$queryRaw<Row[]>(Prisma.sql`
      WITH RECURSIVE category_paths AS (
        SELECT c.id, c.parent_id, ARRAY[c.category_name]::text[] AS path,
               ARRAY[c.id]::bigint[] AS path_ids, c.sensitive AS effective_sensitive
        FROM oa.kb_category c
        WHERE c.parent_id IS NULL AND c.deleted_at IS NULL
        UNION ALL
        SELECT child.id, child.parent_id, parent.path || child.category_name,
               parent.path_ids || child.id,
               parent.effective_sensitive OR child.sensitive
        FROM oa.kb_category child
        JOIN category_paths parent ON child.parent_id = parent.id
        WHERE child.deleted_at IS NULL
      )
      SELECT d.id AS doc_id, a.id AS attachment_id, d.doc_title AS title,
             array_to_string(cp.path, ' / ') AS category,
             d.category_id, c.category_name, cp.path AS category_path,
             cp.path_ids AS category_path_ids,
             cp.effective_sensitive AS category_sensitive,
             d.embedding_status,
             COALESCE(a.original_file_name, a.file_name) AS file_name,
             a.file_size, COALESCE(d.image_total, 0) AS image_total,
             d.created_at,
             COALESCE((SELECT MAX(COALESCE(
                (s.upload_timings->>'completed_at')::timestamptz,
                s.created_at
              ))
              FROM oa.kb_document_source s
              WHERE s.document_id = d.id AND s.deleted_at IS NULL
                AND s.status = 'active'), d.created_at) AS last_uploaded_at,
             d.upload_timings, d.ingest_timings,
             (SELECT COUNT(*) FROM oa.kb_document_source s
              WHERE s.document_id = d.id AND s.deleted_at IS NULL
                AND s.status = 'active')::bigint AS source_count
      FROM oa.kb_document d
      JOIN oa.sys_attachment a ON a.id = d.attachment_id
      JOIN oa.kb_category c ON c.id = d.category_id
      JOIN category_paths cp ON cp.id = d.category_id
      WHERE d.id = ${docId} AND d.deleted_at IS NULL AND d.status = 'active'
      LIMIT 1
    `);
    const row = rows[0];
    if (!row) throw new NotFoundException('知识库文档不存在');
    return {
      doc_id: row.doc_id.toString(),
      attachment_id: row.attachment_id.toString(),
      title: row.title,
      category: row.category ?? row.category_name,
      category_id: row.category_id.toString(),
      category_name: row.category_name,
      category_path: row.category_path,
      category_path_ids: row.category_path_ids.map(String),
      category_sensitive: row.category_sensitive,
      embedding_status: row.embedding_status,
      file_name: row.file_name,
      file_size: row.file_size?.toString() ?? null,
      image_total: Number(row.image_total ?? 0),
      created_at: row.created_at.toISOString(),
      last_uploaded_at: row.last_uploaded_at.toISOString(),
      upload_timings: row.upload_timings,
      ingest_timings: row.ingest_timings,
      source_count: Number(row.source_count),
    };
  }

  private async findExistingByHash(hash: string) {
    return this.prisma.sys_attachment.findFirst({
      where: {
        biz_type: 'knowledge_base',
        file_hash: hash,
        deleted_at: null,
        status: 'active',
        kb_document: { some: { deleted_at: null, status: 'active' } },
      },
      include: {
        kb_document: {
          where: { deleted_at: null, status: 'active' },
          orderBy: { id: 'asc' },
          take: 1,
        },
      },
    });
  }

  /**
   * 回收站软删冲突检查：同一 SHA-256 已存在于回收站时，禁止重复上传，
   * 引导用户先恢复或永久删除。匹配 sys_attachment.status='soft_deleted' 且
   * 其 kb_document 处于 status='deleted' 的记录（也覆盖作为来源附件被软删的情况）。
   */
  private async assertHashNotSoftDeleted(hash: string): Promise<void> {
    const rows = await this.prisma.$queryRaw<
      Array<{ attachment_id: bigint; doc_id: bigint }>
    >(Prisma.sql`
      SELECT a.id AS attachment_id, d.id AS doc_id
      FROM oa.sys_attachment a
      LEFT JOIN oa.kb_document d ON d.attachment_id = a.id
      WHERE a.biz_type = 'knowledge_base'
        AND a.file_hash = ${hash}
        AND a.deleted_at IS NOT NULL
        AND a.status = 'soft_deleted'
      LIMIT 1
    `);
    const hit = rows[0];
    if (hit) {
      throw new ConflictException({
        code: 'SOFT_DELETED_DUPLICATE',
        message: '该文件已存在于回收站，请先恢复或永久删除后再上传',
        doc_id: hit.doc_id?.toString() ?? null,
      });
    }
  }

  private async asUploadResponse(
    existing: NonNullable<ExistingAttachment>,
    deduplicated: boolean,
  ): Promise<KnowledgeDocumentUploadResponse> {
    return {
      document: await this.getSummary(existing.kb_document[0].id),
      deduplicated,
    };
  }

  private async loadTimings(docId: bigint): Promise<{
    upload_timings: ProcessingTimings | null;
    ingest_timings: ProcessingTimings | null;
  }> {
    const rows = await this.prisma.$queryRaw<
      Array<{
        upload_timings: ProcessingTimings | null;
        ingest_timings: ProcessingTimings | null;
      }>
    >(Prisma.sql`
      SELECT upload_timings, ingest_timings
      FROM oa.kb_document
      WHERE id = ${docId}
      LIMIT 1
    `);
    return rows[0] ?? { upload_timings: null, ingest_timings: null };
  }

  private async persistUploadTimings(
    docId: bigint,
    timings: ProcessingTimings,
  ): Promise<void> {
    try {
      await this.prisma.$executeRaw(Prisma.sql`
        UPDATE oa.kb_document
        SET upload_timings = CAST(${JSON.stringify(timings)} AS jsonb)
        WHERE id = ${docId}
      `);
      await this.prisma.$executeRaw(Prisma.sql`
        UPDATE oa.kb_document_source
        SET upload_timings = CAST(${JSON.stringify(timings)} AS jsonb),
            updated_at = NOW()
        WHERE document_id = ${docId} AND is_primary IS TRUE
          AND deleted_at IS NULL AND status = 'active'
      `);
    } catch (error: unknown) {
      this.logger.warn(
        `上传耗时写入失败 doc_id=${docId.toString()}: ${getErrorMessage(error)}`,
      );
    }
  }
}

class UploadTimer {
  private readonly startedAt = new Date();
  private readonly started = performance.now();
  private readonly stages: ProcessingTimings['stages'] = [];

  measureSync<T>(key: string, label: string, operation: () => T): T {
    const started = performance.now();
    try {
      const result = operation();
      this.append(key, label, started, 'success');
      return result;
    } catch (error: unknown) {
      this.append(key, label, started, 'failed');
      throw error;
    }
  }

  record(
    key: string,
    label: string,
    elapsedMs: number,
    status: 'success' | 'failed' | 'skipped',
  ): void {
    this.stages.push({ key, label, elapsed_ms: elapsedMs, status });
  }

  async measure<T>(
    key: string,
    label: string,
    operation: () => Promise<T>,
  ): Promise<T> {
    const started = performance.now();
    try {
      const result = await operation();
      this.append(key, label, started, 'success');
      return result;
    } catch (error: unknown) {
      this.append(key, label, started, 'failed');
      throw error;
    }
  }

  report(status: 'success' | 'failed'): ProcessingTimings {
    return {
      version: 1,
      status,
      started_at: this.startedAt.toISOString(),
      completed_at: new Date().toISOString(),
      total_ms:
        Math.round(Math.max(0, performance.now() - this.started) * 10) / 10,
      stages: [...this.stages],
    };
  }

  private append(
    key: string,
    label: string,
    started: number,
    status: 'success' | 'failed',
  ): void {
    this.stages.push({
      key,
      label,
      elapsed_ms:
        Math.round(Math.max(0, performance.now() - started) * 10) / 10,
      status,
    });
  }
}

export function normalizeFilename(input: string): string {
  const decoded = Buffer.from(input, 'latin1').toString('utf8');
  const candidate = decoded.includes('\uFFFD') ? input : decoded;
  const filename = candidate.replace(/\\/g, '/').split('/').pop()?.trim() ?? '';
  const hasControlCharacter = [...filename].some((character) => {
    const code = character.charCodeAt(0);
    return code <= 31 || code === 127;
  });
  if (!filename || filename.length > 255 || hasControlCharacter) {
    throw new BadRequestException('文件名无效或过长');
  }
  return filename;
}

export function validateKnowledgeFile(
  buffer: Buffer,
  filename: string,
  suppliedMime: string,
): void {
  if (!buffer.length) throw new BadRequestException('不能上传空文件');
  if (buffer.length > MAX_FILE_SIZE)
    throw new BadRequestException('文件不能超过 50MB');
  const ext = extname(filename).toLowerCase();
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    throw new BadRequestException('仅支持 PDF、DOCX、TXT、MD 和常见图片格式');
  }
  const signatureOk = (() => {
    if (ext === '.pdf') return buffer.subarray(0, 5).toString() === '%PDF-';
    if (ext === '.docx') {
      return (
        buffer.subarray(0, 4).equals(Buffer.from([0x50, 0x4b, 0x03, 0x04])) &&
        buffer.includes(Buffer.from('[Content_Types].xml')) &&
        buffer.includes(Buffer.from('word/'))
      );
    }
    if (ext === '.png')
      return buffer
        .subarray(0, 8)
        .equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
    if (ext === '.jpg' || ext === '.jpeg')
      return buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff;
    if (ext === '.webp')
      return (
        buffer.subarray(0, 4).toString() === 'RIFF' &&
        buffer.subarray(8, 12).toString() === 'WEBP'
      );
    if (ext === '.bmp') return buffer.subarray(0, 2).toString() === 'BM';
    if (ext === '.tif' || ext === '.tiff') {
      return (
        buffer.subarray(0, 4).equals(Buffer.from([0x49, 0x49, 0x2a, 0])) ||
        buffer.subarray(0, 4).equals(Buffer.from([0x4d, 0x4d, 0, 0x2a]))
      );
    }
    if (buffer.includes(0)) return false;
    try {
      new TextDecoder('utf-8', { fatal: true }).decode(buffer);
      return true;
    } catch {
      return false;
    }
  })();
  if (!signatureOk)
    throw new BadRequestException('文件内容与扩展名不匹配或文件已损坏');

  const mime = (suppliedMime || 'application/octet-stream').toLowerCase();
  const allowedMimes = compatibleMimeTypes(ext);
  if (mime !== 'application/octet-stream' && !allowedMimes.has(mime)) {
    throw new BadRequestException('文件 MIME 类型与扩展名不匹配');
  }
}

function compatibleMimeTypes(ext: string): Set<string> {
  const mapping: Record<string, string[]> = {
    '.pdf': ['application/pdf'],
    '.docx': [
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/zip',
    ],
    '.txt': ['text/plain'],
    '.md': ['text/markdown', 'text/plain'],
    '.png': ['image/png'],
    '.jpg': ['image/jpeg'],
    '.jpeg': ['image/jpeg'],
    '.webp': ['image/webp'],
    '.bmp': ['image/bmp', 'image/x-ms-bmp'],
    '.tif': ['image/tiff'],
    '.tiff': ['image/tiff'],
  };
  return new Set(mapping[ext] ?? []);
}

function canonicalMimeType(ext: string): string {
  return [...compatibleMimeTypes(ext)][0] ?? 'application/octet-stream';
}

export function sanitizeObjectFilename(filename: string): string {
  const value = filename
    .normalize('NFKC')
    .replace(/[^\p{L}\p{N}._-]+/gu, '_')
    .replace(/^\.+/, '');
  const fallback = `document${extname(filename).toLowerCase()}`;
  return truncateUtf8Filename(value || fallback, 180);
}

function truncateUtf8Filename(filename: string, maxBytes: number): string {
  if (Buffer.byteLength(filename, 'utf8') <= maxBytes) return filename;
  const extension = extname(filename);
  const extensionBytes = Buffer.byteLength(extension, 'utf8');
  const stem = extension ? filename.slice(0, -extension.length) : filename;
  const stemLimit = Math.max(1, maxBytes - extensionBytes);
  let output = '';
  let used = 0;
  for (const character of stem) {
    const bytes = Buffer.byteLength(character, 'utf8');
    if (used + bytes > stemLimit) break;
    output += character;
    used += bytes;
  }
  return `${output || 'document'}${extension}`;
}
