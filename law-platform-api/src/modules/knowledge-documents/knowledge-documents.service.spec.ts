import {
  BadRequestException,
  ConflictException,
  HttpException,
} from '@nestjs/common';
import { MinioService } from '../../core/minio/minio.service';
import { PrismaService } from '../../core/prisma/prisma.service';
import { RagService } from '../rag/rag.service';
import { KnowledgeCategoriesService } from './knowledge-categories.service';
import {
  KnowledgeDocumentsService,
  normalizeFilename,
  sanitizeObjectFilename,
  validateKnowledgeFile,
} from './knowledge-documents.service';

function uploadFile(
  name: string,
  contents: string,
  mimetype: string,
): Express.Multer.File {
  const buffer = Buffer.from(contents, 'utf8');
  return {
    fieldname: 'file',
    originalname: name,
    encoding: '7bit',
    mimetype,
    size: buffer.length,
    buffer,
    destination: '',
    filename: name,
    path: '',
    stream: undefined as never,
  };
}

function categoryService(): KnowledgeCategoriesService {
  return {
    requireAssignable: jest.fn().mockResolvedValue({
      id: BigInt(2),
      name: '法律',
      path: ['法律法规', '法律'],
      pathIds: [BigInt(1), BigInt(2)],
      effectiveSensitive: false,
    }),
  } as unknown as KnowledgeCategoriesService;
}

function categorySummary(row: Record<string, unknown>) {
  return {
    category_id: BigInt(2),
    category_name: '法律',
    category_path: ['法律法规', '法律'],
    category_path_ids: [BigInt(1), BigInt(2)],
    category_sensitive: false,
    source_count: BigInt(1),
    image_total: 0,
    last_uploaded_at: new Date('2026-07-16T00:00:00Z'),
    upload_timings: null,
    ingest_timings: null,
    ...row,
  };
}

describe('KnowledgeDocumentsService', () => {
  const existingAttachment = {
    id: BigInt(8),
    original_file_name: '劳动合同法.md',
    file_name: '劳动合同法.md',
    file_size: BigInt(128),
    kb_document: [
      {
        id: BigInt(12),
        doc_title: '中华人民共和国劳动合同法',
        legal_category: '法规',
        embedding_status: 'success',
        created_at: new Date('2026-07-16T00:00:00Z'),
        category_id: BigInt(2),
      },
    ],
  };

  it('accepts UTF-8 text and rejects spoofed file signatures or MIME types', () => {
    expect(() =>
      validateKnowledgeFile(
        Buffer.from('# 劳动合同法'),
        '劳动合同法.md',
        'text/markdown',
      ),
    ).not.toThrow();
    expect(() =>
      validateKnowledgeFile(
        Buffer.from('not a pdf'),
        'fake.pdf',
        'application/pdf',
      ),
    ).toThrow(BadRequestException);
    expect(() =>
      validateKnowledgeFile(Buffer.from('plain text'), 'note.txt', 'image/png'),
    ).toThrow('文件 MIME 类型与扩展名不匹配');
  });

  it('normalizes browser mojibake filenames without changing safe ASCII names', () => {
    expect(normalizeFilename('law.md')).toBe('law.md');
    expect(normalizeFilename('å³å¨æ³.md')).toBe('劳动法.md');
  });

  it('limits MinIO filename components by UTF-8 bytes and keeps the extension', () => {
    const safe = sanitizeObjectFilename(
      `${'最高人民检察院超长文件名'.repeat(30)}.docx`,
    );

    expect(Buffer.byteLength(safe, 'utf8')).toBeLessThanOrEqual(180);
    expect(safe).toMatch(/\.docx$/);
  });

  it('reuses an exact-content document without uploading or vectorizing again', async () => {
    const prisma = {
      sys_attachment: {
        findFirst: jest.fn().mockResolvedValue(existingAttachment),
      },
      $queryRaw: jest.fn().mockResolvedValue([
        categorySummary({
          doc_id: BigInt(12),
          attachment_id: BigInt(8),
          title: '中华人民共和国劳动合同法',
          category: '法律法规 / 法律',
          embedding_status: 'success',
          file_name: '劳动合同法.md',
          file_size: BigInt(128),
          created_at: new Date('2026-07-16T00:00:00Z'),
        }),
      ]),
    };
    const storage = { uploadFile: jest.fn() };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      {} as RagService,
      categoryService(),
    );

    await expect(
      service.create(
        uploadFile('劳动合同法.md', '# 劳动合同法', 'text/markdown'),
        {
          title: '重复标题不会覆盖原文档',
          category_id: '2',
        },
      ),
    ).resolves.toMatchObject({
      deduplicated: true,
      document: { doc_id: '12', title: '中华人民共和国劳动合同法' },
    });
    expect(storage.uploadFile).not.toHaveBeenCalled();
  });

  it('uploads to MinIO and creates attachment plus public kb_document in one transaction', async () => {
    const attachment = {
      id: BigInt(21),
      original_file_name: '新法规.md',
      file_name: '新法规.md',
      file_size: BigInt(15),
    };
    const document = {
      id: BigInt(31),
      doc_title: '新法规',
      legal_category: '法规',
      embedding_status: 'pending',
      created_at: new Date('2026-07-16T00:00:00Z'),
    };
    const tx = {
      sys_attachment: { create: jest.fn().mockResolvedValue(attachment) },
      kb_document: { create: jest.fn().mockResolvedValue(document) },
      $executeRaw: jest.fn().mockResolvedValue(1),
    };
    const prisma = {
      sys_attachment: { findFirst: jest.fn().mockResolvedValue(null) },
      $transaction: jest.fn((callback: (client: typeof tx) => unknown) =>
        callback(tx),
      ),
      $executeRaw: jest.fn().mockResolvedValue(1),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([])
        .mockResolvedValue([
          categorySummary({
            doc_id: BigInt(31),
            attachment_id: BigInt(21),
            title: '新法规',
            category: '法律法规 / 法律',
            embedding_status: 'pending',
            file_name: '新法规.md',
            file_size: BigInt(15),
            created_at: new Date('2026-07-16T00:00:00Z'),
          }),
        ]),
    };
    const storage = {
      fileExists: jest.fn().mockResolvedValue(false),
      uploadFile: jest.fn().mockResolvedValue({
        bucket: 'law-firm-files',
        objectKey: 'key',
        etag: 'etag',
        size: 15,
      }),
      deleteFile: jest.fn().mockResolvedValue(undefined),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      {} as RagService,
      categoryService(),
    );

    await expect(
      service.create(uploadFile('新法规.md', '# 新法规内容', 'text/markdown'), {
        title: '新法规',
        category_id: '2',
      }),
    ).resolves.toMatchObject({
      deduplicated: false,
      document: { doc_id: '31' },
    });
    /* Jest asymmetric matchers are intentionally typed as any. */

    /* Jest asymmetric matchers are intentionally typed as any. */
    /* eslint-disable @typescript-eslint/no-unsafe-assignment */
    expect(tx.sys_attachment.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          biz_type: 'knowledge_base',
          file_hash: expect.stringMatching(/^[a-f0-9]{64}$/),
          uploaded_by: null,
        }),
      }),
    );
    expect(tx.kb_document.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          permission_level: 'public',
          embedding_status: 'pending',
          created_by: null,
        }),
      }),
    );
    /* eslint-enable @typescript-eslint/no-unsafe-assignment */

    expect(storage.deleteFile).not.toHaveBeenCalled();
    expect(prisma.$executeRaw).toHaveBeenCalledTimes(2);
  });

  it('removes the uploaded object when the database transaction fails', async () => {
    const prisma = {
      sys_attachment: { findFirst: jest.fn().mockResolvedValue(null) },
      $queryRaw: jest.fn().mockResolvedValue([]),
      $transaction: jest
        .fn()
        .mockRejectedValue(new Error('database unavailable')),
    };
    const storage = {
      fileExists: jest.fn().mockResolvedValue(false),
      uploadFile: jest.fn().mockResolvedValue({
        bucket: 'law-firm-files',
        objectKey: 'key',
        etag: 'etag',
        size: 12,
      }),
      deleteFile: jest.fn().mockResolvedValue(undefined),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      {} as RagService,
      categoryService(),
    );

    await expect(
      service.create(uploadFile('failed.md', '# 内容', 'text/markdown'), {
        title: '失败文档',
        category_id: '2',
      }),
    ).rejects.toThrow('database unavailable');
    expect(storage.deleteFile).toHaveBeenCalledWith(
      expect.stringMatching(
        /^knowledge-base\/\d{4}\/\d{2}\/[0-9a-f]{2}\/[0-9a-f]{64}_[0-9a-f]{8}_failed\.md$/,
      ),
      'law-firm-files',
    );
  });

  it('ingests a hidden staging document and promotes it while preserving the target id', async () => {
    const current = {
      id: BigInt(30),
      doc_title: '原标题',
      doc_type: '案例',
      legal_category: '案例',
      category_id: BigInt(2),
      embedding_status: 'success',
      version_no: 'v1',
      permission_level: 'public',
      source_department_id: null,
      author_employee_id: null,
      created_by: null,
      sys_attachment: { id: BigInt(91), file_hash: 'old-hash' },
    };
    const attachment = {
      id: BigInt(101),
      original_file_name: '新版.md',
      file_name: '新版.md',
      file_size: BigInt(20),
    };
    const stagingDocument = { id: BigInt(41) };
    const tx = {
      sys_attachment: { create: jest.fn().mockResolvedValue(attachment) },
      kb_document: { create: jest.fn().mockResolvedValue(stagingDocument) },
    };
    const summaryRow = categorySummary({
      doc_id: BigInt(30),
      attachment_id: BigInt(101),
      title: '新标题',
      category: '法规',
      embedding_status: 'success',
      file_name: '新版.md',
      file_size: BigInt(20),
      image_total: 0,
      created_at: new Date('2026-07-16T00:00:00Z'),
    });
    const prisma = {
      kb_document: { findFirst: jest.fn().mockResolvedValue(current) },
      sys_attachment: { findFirst: jest.fn().mockResolvedValue(null) },
      $transaction: jest.fn((callback: (client: typeof tx) => unknown) =>
        callback(tx),
      ),
      $executeRaw: jest.fn().mockResolvedValue(1),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([])
        .mockResolvedValue([summaryRow]),
    };
    const storage = {
      uploadFile: jest.fn().mockResolvedValue({
        bucket: 'law-firm-files',
        objectKey: 'staging-key',
        etag: 'etag',
        size: 20,
      }),
      deleteFile: jest.fn(),
    };
    const rag = {
      createDocumentRequestId: jest.fn().mockReturnValue('req-replace'),
      ingestDocument: jest.fn().mockResolvedValue({ status: 'success' }),
      promoteDocument: jest.fn().mockResolvedValue({ chunk_count: 4 }),
      cleanupStagingDocument: jest.fn(),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.replace(
        BigInt(30),
        uploadFile('新版.md', '# 新版本内容', 'text/markdown'),
        { title: '新标题', category_id: '2' },
      ),
    ).resolves.toMatchObject({
      replaced: true,
      chunk_count: 4,
      document: { doc_id: '30', title: '新标题' },
    });
    /* eslint-disable @typescript-eslint/no-unsafe-assignment */
    expect(tx.sys_attachment.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ biz_type: 'knowledge_base_staging' }),
      }),
    );
    expect(tx.kb_document.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ status: 'staging' }),
      }),
    );
    /* eslint-enable @typescript-eslint/no-unsafe-assignment */
    expect(rag.ingestDocument).toHaveBeenCalledWith('41', true, {
      routingDocId: '30',
      requestId: 'req-replace',
    });
    expect(rag.promoteDocument).toHaveBeenCalledWith('41', '30', 'req-replace');
    expect(rag.cleanupStagingDocument).not.toHaveBeenCalled();
  });

  it('appends a source through staging and keeps the original document id', async () => {
    const current = {
      id: BigInt(30),
      doc_title: '多源知识库',
      doc_type: '工作资料',
      legal_category: '工作资料',
      category_id: BigInt(2),
      embedding_status: 'success',
      version_no: 'v1',
      permission_level: 'public',
      source_department_id: null,
      author_employee_id: null,
      created_by: null,
      sys_attachment: { id: BigInt(91), file_hash: 'old-hash' },
    };
    const attachment = {
      id: BigInt(102),
      original_file_name: '后续.md',
      file_name: '后续.md',
      file_size: BigInt(20),
    };
    const tx = {
      sys_attachment: { create: jest.fn().mockResolvedValue(attachment) },
      kb_document: { create: jest.fn().mockResolvedValue({ id: BigInt(42) }) },
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ next_order: 1 }])
        .mockResolvedValueOnce([{ id: BigInt(82) }]),
    };
    const sourceRow = {
      source_id: BigInt(82),
      document_id: BigInt(30),
      attachment_id: BigInt(102),
      source_title: '后续材料',
      sort_order: 1,
      is_primary: false,
      ingest_status: 'success',
      chunk_count: 2,
      image_total: 0,
      image_kept: 0,
      image_filtered: 0,
      uploaded_at: new Date('2026-07-16T01:00:00Z'),
      file_name: '后续.md',
      file_size: BigInt(20),
      upload_timings: null,
      ingest_timings: null,
    };
    const summaryRow = categorySummary({
      doc_id: BigInt(30),
      attachment_id: BigInt(91),
      title: '多源知识库',
      category: '工作资料',
      embedding_status: 'success',
      file_name: '主文件.md',
      file_size: BigInt(20),
      source_count: BigInt(2),
      image_total: 0,
      created_at: new Date('2026-07-16T00:00:00Z'),
    });
    const prisma = {
      kb_document: { findFirst: jest.fn().mockResolvedValue(current) },
      $transaction: jest.fn((callback: (client: typeof tx) => unknown) =>
        callback(tx),
      ),
      $executeRaw: jest.fn().mockResolvedValue(1),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([sourceRow])
        .mockResolvedValueOnce([summaryRow]),
    };
    const storage = {
      uploadFile: jest.fn().mockResolvedValue({
        bucket: 'law-firm-files',
        objectKey: 'staging-source-key',
        etag: 'etag',
        size: 20,
      }),
      deleteFile: jest.fn(),
    };
    const rag = {
      createDocumentRequestId: jest.fn().mockReturnValue('req-append'),
      ingestDocument: jest.fn().mockResolvedValue({ status: 'success' }),
      promoteSource: jest.fn().mockResolvedValue({ chunk_count: 5 }),
      cleanupStagingDocument: jest.fn(),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.appendSource(
        BigInt(30),
        uploadFile('后续.md', '# 后续来源内容', 'text/markdown'),
        { source_title: '后续材料' },
      ),
    ).resolves.toMatchObject({
      document: { doc_id: '30', source_count: 2 },
      source: { source_id: '82', source_title: '后续材料' },
      chunk_count: 5,
    });
    expect(rag.promoteSource).toHaveBeenCalledWith(
      expect.objectContaining({
        stagingDocId: '42',
        targetDocId: '30',
        sourceId: '82',
        mode: 'append',
        requestId: 'req-append',
      }),
    );
    expect(rag.cleanupStagingDocument).not.toHaveBeenCalled();
    expect(storage.deleteFile).not.toHaveBeenCalled();
  });

  it('batch moves active documents to another category in one update', async () => {
    const prisma = {
      $executeRaw: jest.fn().mockResolvedValue(2),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ id: BigInt(10) }, { id: BigInt(11) }]),
    };
    const storage = { deleteFile: jest.fn() };
    const rag = { batchDeleteDocuments: jest.fn() };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.batchMove({ doc_ids: ['10', '11'], category_id: '2' }),
    ).resolves.toEqual({
      moved: 2,
      category_id: '2',
      category_path: ['法律法规', '法律'],
    });
    expect(prisma.$executeRaw).toHaveBeenCalledTimes(1);
    expect(rag.batchDeleteDocuments).not.toHaveBeenCalled();
    expect(storage.deleteFile).not.toHaveBeenCalled();
  });

  it('updates only the document title and preserves the last upload time', async () => {
    const lastUploadedAt = new Date('2026-07-16T06:30:00Z');
    const prisma = {
      kb_document: {
        findFirst: jest.fn().mockResolvedValue({ id: BigInt(30) }),
      },
      $executeRaw: jest.fn().mockResolvedValue(1),
      $queryRaw: jest.fn().mockResolvedValue([
        categorySummary({
          doc_id: BigInt(30),
          attachment_id: BigInt(91),
          title: '修改后的标题',
          category: '法律法规 / 法律',
          embedding_status: 'success',
          file_name: '原文件.md',
          file_size: BigInt(20),
          created_at: new Date('2026-07-16T00:00:00Z'),
          last_uploaded_at: lastUploadedAt,
        }),
      ]),
    };
    const rag = {
      ingestDocument: jest.fn(),
      promoteSource: jest.fn(),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      {} as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.updateTitle(BigInt(30), { title: '修改后的标题' }),
    ).resolves.toMatchObject({
      doc_id: '30',
      title: '修改后的标题',
      last_uploaded_at: lastUploadedAt.toISOString(),
    });
    expect(prisma.$executeRaw).toHaveBeenCalledTimes(1);
    expect(rag.ingestDocument).not.toHaveBeenCalled();
    expect(rag.promoteSource).not.toHaveBeenCalled();
  });

  it('returns source upload time and document last upload time', async () => {
    const sourceUploadedAt = new Date('2026-07-16T08:30:15Z');
    const documentUploadedAt = new Date('2026-07-16T09:45:00Z');
    const prisma = {
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([
          {
            source_id: BigInt(81),
            document_id: BigInt(24),
            attachment_id: BigInt(56),
            source_title: 'test.md',
            file_name: 'test.md',
            file_size: BigInt(18),
            sort_order: 0,
            is_primary: true,
            ingest_status: 'success',
            chunk_count: 1,
            image_total: 0,
            uploaded_at: sourceUploadedAt,
            upload_timings: null,
            ingest_timings: null,
          },
        ])
        .mockResolvedValueOnce([
          categorySummary({
            doc_id: BigInt(24),
            attachment_id: BigInt(56),
            title: '测试法规',
            category: '法律法规 / 法律',
            embedding_status: 'success',
            file_name: 'test.md',
            file_size: BigInt(18),
            created_at: new Date('2026-07-16T00:00:00Z'),
            last_uploaded_at: documentUploadedAt,
          }),
        ])
        .mockResolvedValueOnce([{ total: BigInt(1) }]),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      {} as MinioService,
      {} as RagService,
      categoryService(),
    );

    await expect(service.listSources(BigInt(24))).resolves.toMatchObject({
      items: [{ uploaded_at: sourceUploadedAt.toISOString() }],
    });
    await expect(
      service.list({ page: 1, page_size: 5 }),
    ).resolves.toMatchObject({
      items: [{ last_uploaded_at: documentUploadedAt.toISOString() }],
    });
  });

  it('lists legacy knowledge documents without filtering by attachment biz_type', async () => {
    const statements: string[] = [];
    const queryRaw = jest.fn((query: { strings: readonly string[] }) => {
      const statement = query.strings.join(' ');
      statements.push(statement);
      return Promise.resolve(
        statement.includes('COUNT(*)::bigint AS total')
          ? [{ total: BigInt(0) }]
          : [],
      );
    });
    const prisma = { $queryRaw: queryRaw };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      {} as MinioService,
      {} as RagService,
      categoryService(),
    );

    await expect(
      service.list({ page: 1, page_size: 5, category_id: '4' }),
    ).resolves.toMatchObject({ items: [], total: 0 });
    expect(statements.join(' ')).not.toContain("a.biz_type = 'knowledge_base'");
  });

  it('batch soft-deletes active documents without touching MinIO or RAG', async () => {
    const tx = { $executeRaw: jest.fn().mockResolvedValue(1) };
    const prisma = {
      $transaction: jest.fn((callback: (client: typeof tx) => unknown) =>
        callback(tx),
      ),
      $executeRaw: jest.fn().mockResolvedValue(1),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ id: BigInt(10) }, { id: BigInt(11) }])
        .mockResolvedValueOnce([
          {
            id: BigInt(20),
            bucket: 'law-firm-files',
            object_key: 'doc/10/file',
          },
          {
            id: BigInt(21),
            bucket: 'law-firm-files',
            object_key: 'doc/11/file',
          },
        ]),
    };
    const storage = { deleteFile: jest.fn().mockResolvedValue(undefined) };
    const rag = {
      batchDeleteDocuments: jest.fn().mockResolvedValue(undefined),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.batchDelete({ doc_ids: ['10', '11'] }),
    ).resolves.toEqual({
      deleted: 2,
      mode: 'soft',
      artifacts_retained: true,
    });
    // 纯软删除：三张表状态翻转（kb_document、kb_document_source、sys_attachment）
    expect(tx.$executeRaw).toHaveBeenCalledTimes(3);
    // 不删除 MinIO 原件，也不调用 RAG 清理 —— 原件/图片/向量全部保留以便恢复
    expect(storage.deleteFile).not.toHaveBeenCalled();
    expect(rag.batchDeleteDocuments).not.toHaveBeenCalled();
  });

  it('batch delete rejects when any document is missing or inactive', async () => {
    const prisma = {
      $queryRaw: jest.fn().mockResolvedValue([{ id: BigInt(10) }]),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      {} as MinioService,
      {} as RagService,
      categoryService(),
    );

    await expect(
      service.batchDelete({ doc_ids: ['10', '11'] }),
    ).rejects.toThrow('部分知识库文档不存在或已删除');
  });

  it('create rejects with SOFT_DELETED_DUPLICATE when hash is in the trash', async () => {
    const prisma = {
      sys_attachment: {
        findFirst: jest.fn().mockResolvedValue(null),
      },
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([]) // findSourceByHash: 无活动来源
        .mockResolvedValueOnce([
          { attachment_id: BigInt(20), doc_id: BigInt(30) },
        ]), // assertHashNotSoftDeleted: 回收站命中
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      { fileExists: jest.fn() } as unknown as MinioService,
      {} as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.create(uploadFile('a.md', '# 测试文档', 'text/markdown'), {
        category_id: '2',
        title: '测试文档',
      }),
    ).rejects.toMatchObject({
      status: 409,
      response: { code: 'SOFT_DELETED_DUPLICATE' },
    });
  });

  it('listTrash paginates soft-deleted docs and resolves category_valid', async () => {
    const prisma = {
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([
          {
            doc_id: BigInt(30),
            attachment_id: BigInt(20),
            title: '已删除文档',
            category_id: BigInt(2),
            category_name: '法律',
            category_path: ['法律法规', '法律'],
            category_path_ids: [BigInt(1), BigInt(2)],
            category_valid: true,
            deleted_at: new Date('2026-07-19T00:00:00Z'),
            embedding_status: 'success',
            file_name: 'a.md',
            file_size: BigInt(128),
            source_count: BigInt(1),
          },
        ])
        .mockResolvedValueOnce([{ total: BigInt(1) }]),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      {} as unknown as MinioService,
      {} as unknown as RagService,
      categoryService(),
    );

    const result = await service.listTrash({
      page: 1,
      page_size: 20,
      sort: 'deleted_at',
      order: 'desc',
    });
    expect(result.total).toBe(1);
    expect(result.items[0]).toMatchObject({
      doc_id: '30',
      category_valid: true,
      restorable: true,
      file_size: '128',
      source_count: 1,
    });
  });

  it('batchRestore restores docs when originals and RAG artifacts are intact', async () => {
    const tx = { $executeRaw: jest.fn().mockResolvedValue(1) };
    const prisma = {
      $transaction: jest.fn((cb: (c: typeof tx) => unknown) => cb(tx)),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ id: BigInt(10) }]) // requireDeletedDocuments
        .mockResolvedValueOnce([{ id: BigInt(10), category_valid: true }]) // 分类有效性
        .mockResolvedValueOnce([
          { id: BigInt(20), bucket: 'law-firm-files', object_key: 'kb/10/f' },
        ]), // 原件
    };
    const storage = { fileExists: jest.fn().mockResolvedValue(true) };
    const rag = {
      verifyRestoreDocuments: jest.fn().mockResolvedValue({
        request_id: 'req-restore',
        items: [
          { doc_id: 10, ok: true, missing_chunks: 0, missing_images: [] },
        ],
      }),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(service.batchRestore({ doc_ids: ['10'] })).resolves.toEqual({
      restored: 1,
      doc_ids: ['10'],
      request_id: 'req-restore',
    });
    expect(tx.$executeRaw).toHaveBeenCalledTimes(3);
  });

  it('batchRestore rejects with RESTORE_ORIGINAL_MISSING and writes nothing', async () => {
    const tx = { $executeRaw: jest.fn() };
    const prisma = {
      $transaction: jest.fn((cb: (c: typeof tx) => unknown) => cb(tx)),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ id: BigInt(10) }])
        .mockResolvedValueOnce([{ id: BigInt(10), category_valid: true }])
        .mockResolvedValueOnce([
          { id: BigInt(20), bucket: 'law-firm-files', object_key: 'kb/10/f' },
        ]),
    };
    const storage = { fileExists: jest.fn().mockResolvedValue(false) };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      {} as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.batchRestore({ doc_ids: ['10'] }),
    ).rejects.toMatchObject({ response: { code: 'RESTORE_ORIGINAL_MISSING' } });
    expect(tx.$executeRaw).not.toHaveBeenCalled();
  });

  it('batchRestore rejects with RESTORE_ARTIFACTS_MISSING when vectors/images gone', async () => {
    const tx = { $executeRaw: jest.fn() };
    const prisma = {
      $transaction: jest.fn((cb: (c: typeof tx) => unknown) => cb(tx)),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ id: BigInt(10) }])
        .mockResolvedValueOnce([{ id: BigInt(10), category_valid: true }])
        .mockResolvedValueOnce([
          { id: BigInt(20), bucket: 'law-firm-files', object_key: 'kb/10/f' },
        ]),
    };
    const storage = { fileExists: jest.fn().mockResolvedValue(true) };
    const rag = {
      verifyRestoreDocuments: jest.fn().mockResolvedValue({
        request_id: 'req-restore-failed',
        items: [
          { doc_id: 10, ok: false, missing_chunks: 1, missing_images: [] },
        ],
      }),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.batchRestore({ doc_ids: ['10'] }),
    ).rejects.toMatchObject({
      response: { code: 'RESTORE_ARTIFACTS_MISSING' },
    });
    expect(tx.$executeRaw).not.toHaveBeenCalled();
  });

  it('batchRestore rejects with RESTORE_CATEGORY_INVALID when category lapsed and no override', async () => {
    const prisma = {
      $transaction: jest.fn(),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ id: BigInt(10) }])
        .mockResolvedValueOnce([{ id: BigInt(10), category_valid: false }]),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      {} as unknown as MinioService,
      {} as unknown as RagService,
      categoryService(),
    );

    await expect(
      service.batchRestore({ doc_ids: ['10'] }),
    ).rejects.toMatchObject({ response: { code: 'RESTORE_CATEGORY_INVALID' } });
    expect(prisma.$transaction).not.toHaveBeenCalled();
  });

  it('batchPurge purges deleted docs via RAG and marks them purged', async () => {
    const tx = { $executeRaw: jest.fn().mockResolvedValue(1) };
    const prisma = {
      $transaction: jest.fn((cb: (c: typeof tx) => unknown) => cb(tx)),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ id: BigInt(10), status: 'deleted' }])
        .mockResolvedValueOnce([
          { id: BigInt(20), bucket: 'law-firm-files', object_key: 'kb/10/f' },
        ]),
    };
    const storage = { deleteFile: jest.fn().mockResolvedValue(undefined) };
    const rag = {
      batchDeleteDocuments: jest.fn().mockResolvedValue('req-purge'),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(service.batchPurge({ doc_ids: ['10'] })).resolves.toEqual({
      purged: 1,
      already_purged: 0,
      request_id: 'req-purge',
    });
    expect(rag.batchDeleteDocuments).toHaveBeenCalledWith(['10']);
    expect(tx.$executeRaw).toHaveBeenCalledTimes(3);
  });

  it('batchPurge is idempotent for already-purged docs', async () => {
    const tx = { $executeRaw: jest.fn() };
    const prisma = {
      $transaction: jest.fn((cb: (c: typeof tx) => unknown) => cb(tx)),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ id: BigInt(10), status: 'purged' }]),
    };
    const rag = { batchDeleteDocuments: jest.fn() };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      {} as unknown as MinioService,
      rag as unknown as RagService,
      categoryService(),
    );

    await expect(service.batchPurge({ doc_ids: ['10'] })).resolves.toEqual({
      purged: 0,
      already_purged: 1,
    });
    expect(rag.batchDeleteDocuments).not.toHaveBeenCalled();
    expect(tx.$executeRaw).not.toHaveBeenCalled();
  });

  it('preserves sanitized upstream errors and request ids in composite operations', () => {
    const service = new KnowledgeDocumentsService(
      {} as PrismaService,
      {} as MinioService,
      {} as RagService,
      categoryService(),
    );
    const rethrower = service as unknown as {
      rethrowSourceError(
        error: unknown,
        message: string,
        requestId: string,
      ): never;
    };
    const loggerError = jest
      .spyOn(
        (
          service as unknown as {
            logger: { error(message: string): void };
          }
        ).logger,
        'error',
      )
      .mockImplementation(() => undefined);
    const upstream = new HttpException(
      {
        code: 'RAG_REQUEST_REJECTED',
        message: '文档处理服务暂不可用',
        request_id: 'req-upstream',
      },
      503,
    );

    expect(() =>
      rethrower.rethrowSourceError(upstream, '安全摘要', 'req-upstream'),
    ).toThrow(upstream);

    let caught: unknown;
    try {
      rethrower.rethrowSourceError(
        new Error(String.raw`C:\private\case.pdf postgres://password@db`),
        '源文件处理失败',
        'req-local',
      );
    } catch (error: unknown) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ConflictException);
    expect(caught).toMatchObject({
      response: {
        code: 'RAG_DOCUMENT_OPERATION_FAILED',
        message: '源文件处理失败',
        request_id: 'req-local',
      },
    });
    expect(JSON.stringify(caught)).not.toMatch(/private|postgres|password/i);
    expect(loggerError).toHaveBeenCalledWith(
      expect.stringMatching(/private.*postgres.*password/i),
    );
  });
});
