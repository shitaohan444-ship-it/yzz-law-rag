import { Injectable, Logger } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../../core/prisma/prisma.service';
import { MinioService } from '../../core/minio/minio.service';
import { getErrorMessage } from '../../common/error-message';

/**
 * 附件业务服务：把 MinIO 对象存储与 sys_attachment / sys_attachment_relation 串联。
 * 对照 Python `law-rag-service/app/services/attachment_service.py`，并在重写时修复两个缺陷：
 *   1. upload：MinIO put 在事务外先做；DB 写包进 $transaction，失败则补偿删除已传对象
 *   2. delete：改为「先提交 DB 软删 → 后删 MinIO」，避免「行还在但对象已丢」的不可恢复脏状态
 *
 * 事务边界约定：
 *   - upload / delete 自持事务边界（需感知提交成功才能补偿/后置删除），不接收外部 tx
 *   - bindToEntity 是纯 DB 写，接收 Prisma.TransactionClient，可组合进调用方事务
 */
/** biz_type 语义码 → (prefix, 表名, 编号列)，用于自动解析 entity_no */
const BIZ_ENTITY_MAP: Record<string, [string, string, string]> = {
  case: ['cases', 'case_main', 'case_no'],
  案件: ['cases', 'case_main', 'case_no'],
  lead: ['leads', 'crm_lead', 'lead_no'],
  线索: ['leads', 'crm_lead', 'lead_no'],
  fee_agreement: ['contracts', 'fin_fee_agreement', 'agreement_no'],
  收费协议: ['contracts', 'fin_fee_agreement', 'agreement_no'],
  contract: ['contracts', 'fin_fee_agreement', 'agreement_no'],
};

export interface UploadInput {
  fileData: Buffer;
  filename: string;
  bizType: string;
  bizId: bigint;
  category: string;
  uploadedBy: bigint;
  contentType?: string;
  prefix?: string;
  entityNo?: string;
  /** 提供则同步写 sys_attachment_relation */
  entityType?: string;
  entityId?: bigint;
  fileUsage?: number;
}

@Injectable()
export class AttachmentService {
  private readonly logger = new Logger(AttachmentService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly storage: MinioService,
  ) {}

  /** 上传到 MinIO + 写 sys_attachment（+可选 relation）。返回 sys_attachment.id。 */
  async upload(input: UploadInput): Promise<bigint> {
    // 1. 解析 prefix / entityNo
    let prefix = input.prefix;
    let entityNo = input.entityNo;
    if (!prefix || !entityNo) {
      const [p, n] = await this.resolveEntityNo(input.bizType, input.bizId);
      prefix = prefix ?? p;
      entityNo = entityNo ?? n;
    }

    // 2. 生成 object_key（UTC）
    const now = new Date();
    const objectKey = MinioService.buildObjectKey(prefix, {
      filename: input.filename,
      year: now.getUTCFullYear(),
      month: now.getUTCMonth() + 1,
      entityNo,
      category: input.category,
    });

    // 3. 上传 MinIO（事务外，先做）
    const result = await this.storage.uploadFile(objectKey, input.fileData, {
      contentType: input.contentType,
    });

    // 4. 写库（事务内）；失败则补偿删除已上传对象
    try {
      return await this.prisma.$transaction(async (tx) => {
        const dotIdx = input.filename.lastIndexOf('.');
        const ext =
          dotIdx >= 0 ? input.filename.slice(dotIdx + 1).toLowerCase() : '';
        const mime =
          input.contentType ??
          MinioService.guessContentType(input.filename) ??
          'application/octet-stream';
        const baseName = objectKey.slice(objectKey.lastIndexOf('/') + 1);

        const created = await tx.sys_attachment.create({
          data: {
            biz_type: input.bizType,
            biz_id: input.bizId,
            file_name: input.filename,
            file_ext: ext,
            mime_type: mime,
            file_size: BigInt(result.size),
            storage_type: 'minio',
            storage_path: objectKey,
            bucket: result.bucket,
            object_key: objectKey,
            etag: result.etag,
            original_file_name: input.filename,
            current_file_name: baseName,
            uploaded_by: input.uploadedBy,
            uploaded_at: now,
            created_at: now,
            created_by: input.uploadedBy,
            updated_at: now,
            updated_by: input.uploadedBy,
            status: 'active',
            file_exists_flag: '1',
            ai_index_status: 'pending',
          },
        });

        if (input.entityType && input.entityId != null) {
          await tx.sys_attachment_relation.create({
            data: {
              attachment_id: created.id,
              entity_type: input.entityType,
              entity_id: input.entityId,
              file_usage: input.fileUsage ?? null,
              sort_order: 0,
              is_primary: 0,
              created_at: now,
              created_by: input.uploadedBy,
              updated_at: now,
              updated_by: input.uploadedBy,
            },
          });
        }

        return created.id;
      });
    } catch (e) {
      this.logger.warn(
        `写库失败，回滚已上传的 MinIO 对象 ${objectKey}: ${getErrorMessage(e)}`,
      );
      await this.storage.deleteFile(objectKey).catch((err) => {
        this.logger.error(`补偿删除失败 ${objectKey}: ${getErrorMessage(err)}`);
      });
      throw e;
    }
  }

  /** 下载附件，返回 Buffer。 */
  async download(attachmentId: bigint): Promise<Buffer> {
    const att = await this.getActive(attachmentId);
    const objectKey = att.object_key ?? att.storage_path;
    if (!objectKey) throw new Error(`附件无 object_key: id=${attachmentId}`);
    return this.storage.downloadFile(objectKey);
  }

  /** 取附件下载所需的完整信息（buffer + mime + 文件名），供 HTTP 下载端点用。 */
  async getDownload(
    attachmentId: bigint,
  ): Promise<{ buffer: Buffer; mimeType: string; fileName: string }> {
    const att = await this.getActive(attachmentId);
    const objectKey = att.object_key ?? att.storage_path;
    if (!objectKey) throw new Error(`附件无 object_key: id=${attachmentId}`);
    const buffer = await this.storage.downloadFile(objectKey);
    return {
      buffer,
      mimeType: att.mime_type ?? 'application/octet-stream',
      fileName:
        att.original_file_name ?? att.file_name ?? `attachment_${attachmentId}`,
    };
  }

  /** 写 sys_attachment_relation（自持事务，HTTP 单次绑定用）。返回 relation.id。 */
  async bind(input: {
    attachmentId: bigint;
    entityType: string;
    entityId: bigint;
    fileUsage?: number | null;
    isPrimary?: number;
    operatorId?: bigint | null;
  }): Promise<bigint> {
    return this.prisma.$transaction((tx) => this.bindToEntity(tx, input));
  }

  /** 生成预签名 URL。 */
  async getPresignedUrl(attachmentId: bigint, expires = 3600): Promise<string> {
    const att = await this.getActive(attachmentId);
    const objectKey = att.object_key ?? att.storage_path;
    if (!objectKey) throw new Error(`附件无 object_key: id=${attachmentId}`);
    return this.storage.getPresignedUrl(objectKey, { expires });
  }

  /** 删除：先提交 DB（软删/硬删），后删 MinIO。 */
  async delete(attachmentId: bigint, soft = true): Promise<void> {
    const now = new Date();
    const objectKey = await this.prisma.$transaction(async (tx) => {
      const att = await tx.sys_attachment.findUnique({
        where: { id: attachmentId },
      });
      if (!att || att.deleted_at) {
        throw new Error(`附件不存在或已删除: id=${attachmentId}`);
      }
      if (soft) {
        await tx.sys_attachment.update({
          where: { id: attachmentId },
          data: { deleted_at: now, updated_at: now },
        });
      } else {
        await tx.sys_attachment_relation.deleteMany({
          where: { attachment_id: attachmentId },
        });
        await tx.sys_attachment.delete({ where: { id: attachmentId } });
      }
      return att.object_key ?? att.storage_path;
    });

    if (objectKey) {
      await this.storage.deleteFile(objectKey).catch((err) => {
        this.logger.warn(
          `MinIO 删除失败（DB 已一致，留待扫描补救）${objectKey}: ${getErrorMessage(err)}`,
        );
      });
    }
  }

  /** 写 sys_attachment_relation（纯 DB 写，接收 tx 以便组合进调用方事务）。返回 relation.id。 */
  async bindToEntity(
    tx: Prisma.TransactionClient,
    input: {
      attachmentId: bigint;
      entityType: string;
      entityId: bigint;
      fileUsage?: number | null;
      isPrimary?: number;
      operatorId?: bigint | null;
    },
  ): Promise<bigint> {
    const now = new Date();
    const created = await tx.sys_attachment_relation.create({
      data: {
        attachment_id: input.attachmentId,
        entity_type: input.entityType,
        entity_id: input.entityId,
        file_usage: input.fileUsage ?? null,
        sort_order: 0,
        is_primary: input.isPrimary ?? 0,
        created_at: now,
        created_by: input.operatorId ?? null,
        updated_at: now,
        updated_by: input.operatorId ?? null,
      },
    });
    return created.id;
  }

  private async getActive(attachmentId: bigint) {
    const att = await this.prisma.sys_attachment.findUnique({
      where: { id: attachmentId },
    });
    if (!att || att.deleted_at) {
      throw new Error(`附件不存在或已删除: id=${attachmentId}`);
    }
    return att;
  }

  /** 解析 prefix 与 entity_no（biz_type 命中映射则按编号列查，未命中或查无行则回退 bizId）。 */
  private async resolveEntityNo(
    bizType: string,
    bizId: bigint,
  ): Promise<[string, string]> {
    const entry = BIZ_ENTITY_MAP[bizType];
    if (!entry) return ['misc', bizId.toString()];
    const [prefix, table, col] = entry;
    // table/col 来自白名单常量（防注入）；bizId 走参数化
    const rows = await this.prisma.$queryRaw<{ no: string | null }[]>`
      SELECT ${Prisma.raw(`"${col}"`)} AS no
      FROM "oa"."${Prisma.raw(table)}"
      WHERE id = ${bizId}
    `;
    const no = rows[0]?.no;
    return [prefix, no ? String(no) : bizId.toString()];
  }
}
