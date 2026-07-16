import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../../core/prisma/prisma.service';
import { AttachmentService } from '../attachments/attachment.service';
import { getErrorMessage } from '../../common/error-message';

/**
 * 案件材料服务（case_material 业务层）+ 附件服务集成。
 *
 * 两层模型：case_material（业务）→ sys_attachment（文件，经 AttachmentService 管理）。
 *
 * 事务一致性（方案 A 补偿式）：
 *  - 建材料带文件 / 后补文件：先 attachments.upload（自持事务+MinIO 副作用，已提交）→
 *    再 $transaction 写/改 case_material → 失败则 attachments.delete 补偿。
 *  - upload 无法包进外部 Prisma tx（无 XA），故用补偿。补偿失败留孤儿附件，由后续 sweeper 兜底。
 *  - 软删材料：先软删 case_material → 若有附件则级联 attachments.delete（软删附件+删 MinIO）。
 */
@Injectable()
export class CaseMaterialService {
  private readonly logger = new Logger(CaseMaterialService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly attachments: AttachmentService,
  ) {}

  /** 建材料带文件：upload → $transaction 写 case_material → 失败补偿。 */
  async createWithFile(input: {
    caseId: bigint;
    fileData: Buffer;
    filename: string;
    contentType?: string;
    materialName: string;
    materialType: string;
    category: string;
    sourceFrom?: string;
    receivedAt?: Date;
    receivedBy?: bigint;
    uploadedBy: bigint;
    remark?: string;
  }): Promise<{ id: bigint }> {
    // 1. 上传文件（已提交：MinIO 对象 + sys_attachment 行）
    const attachmentId = await this.attachments.upload({
      fileData: input.fileData,
      filename: input.filename,
      bizType: 'case',
      bizId: input.caseId,
      category: input.category,
      contentType: input.contentType,
      uploadedBy: input.uploadedBy,
    });

    // 2. 写 case_material；失败则补偿删附件
    try {
      return await this.prisma.$transaction(async (tx) => {
        const now = new Date();
        const m = await tx.case_material.create({
          data: {
            case_id: input.caseId,
            material_name: input.materialName,
            material_type: input.materialType,
            source_from: input.sourceFrom ?? null,
            received_at: input.receivedAt ?? null,
            received_by: input.receivedBy ?? null,
            attachment_id: attachmentId,
            nas_path: null,
            review_status: 'pending',
            created_at: now,
            created_by: input.uploadedBy,
            updated_at: now,
            updated_by: input.uploadedBy,
            status: 'active',
            remark: input.remark ?? null,
          },
        });
        return { id: m.id };
      });
    } catch (e) {
      this.logger.warn(
        `写 case_material 失败，补偿删附件 ${attachmentId}: ${getErrorMessage(e)}`,
      );
      await this.attachments.delete(attachmentId, true).catch((err) => {
        this.logger.error(
          `补偿删附件失败 ${attachmentId}: ${getErrorMessage(err)}`,
        );
      });
      throw e;
    }
  }

  /** 纯登记材料（无文件，attachment_id 空，可填 nas_path）。单行写，不包事务。 */
  async createRegistration(input: {
    caseId: bigint;
    materialName: string;
    materialType: string;
    sourceFrom?: string;
    receivedAt?: Date;
    receivedBy?: bigint;
    nasPath?: string;
    uploadedBy: bigint;
    remark?: string;
  }): Promise<{ id: bigint }> {
    const now = new Date();
    const m = await this.prisma.case_material.create({
      data: {
        case_id: input.caseId,
        material_name: input.materialName,
        material_type: input.materialType,
        source_from: input.sourceFrom ?? null,
        received_at: input.receivedAt ?? null,
        received_by: input.receivedBy ?? null,
        attachment_id: null,
        nas_path: input.nasPath ?? null,
        review_status: 'pending',
        created_at: now,
        created_by: input.uploadedBy,
        updated_at: now,
        updated_by: input.uploadedBy,
        status: 'active',
        remark: input.remark ?? null,
      },
    });
    return { id: m.id };
  }

  /** 案件下材料列表（分页 + 过滤 + 附件元信息）。 */
  async listByCase(
    caseId: bigint,
    query: {
      materialType?: string;
      hasFile?: boolean;
      reviewStatus?: string;
      page: number;
      pageSize: number;
    },
  ) {
    const where: Record<string, unknown> = {
      case_id: caseId,
      deleted_at: null,
    };
    if (query.materialType) where.material_type = query.materialType;
    if (query.reviewStatus) where.review_status = query.reviewStatus;
    if (query.hasFile === true) where.attachment_id = { not: null };
    else if (query.hasFile === false) where.attachment_id = null;

    const attachmentSelect = {
      id: true,
      file_name: true,
      file_size: true,
      mime_type: true,
      file_ext: true,
      uploaded_at: true,
    };

    const [items, total] = await Promise.all([
      this.prisma.case_material.findMany({
        where,
        include: {
          sys_attachment: {
            where: { deleted_at: null },
            select: attachmentSelect,
          },
        },
        orderBy: { created_at: 'desc' },
        skip: (query.page - 1) * query.pageSize,
        take: query.pageSize,
      }),
      this.prisma.case_material.count({ where }),
    ]);
    return { items, total, page: query.page, pageSize: query.pageSize };
  }

  /** 材料详情（含附件元信息）。 */
  async findOne(id: bigint) {
    const m = await this.prisma.case_material.findUnique({
      where: { id },
      include: {
        sys_attachment: {
          where: { deleted_at: null },
          select: {
            id: true,
            file_name: true,
            file_size: true,
            mime_type: true,
            file_ext: true,
            uploaded_at: true,
          },
        },
      },
    });
    if (!m || m.deleted_at) throw new NotFoundException(`材料不存在: id=${id}`);
    return m;
  }

  /** 改材料元数据（不含文件）。 */
  async update(
    id: bigint,
    input: {
      materialName?: string;
      materialType?: string;
      sourceFrom?: string;
      receivedAt?: Date;
      receivedBy?: bigint;
      remark?: string;
      updatedBy: bigint;
    },
  ) {
    await this.findOne(id); // 校验存在 + 未删
    const now = new Date();
    const data: Record<string, unknown> = {
      updated_at: now,
      updated_by: input.updatedBy,
    };
    if (input.materialName !== undefined)
      data.material_name = input.materialName;
    if (input.materialType !== undefined)
      data.material_type = input.materialType;
    if (input.sourceFrom !== undefined) data.source_from = input.sourceFrom;
    if (input.receivedAt !== undefined) data.received_at = input.receivedAt;
    if (input.receivedBy !== undefined) data.received_by = input.receivedBy;
    if (input.remark !== undefined) data.remark = input.remark;
    return this.prisma.case_material.update({ where: { id }, data });
  }

  /** 后补/替换文件：upload 新 → 更新指针（失败补偿删新）→ 成功后软删旧。 */
  async replaceFile(
    id: bigint,
    input: {
      fileData: Buffer;
      filename: string;
      contentType?: string;
      category: string;
      uploadedBy: bigint;
    },
  ): Promise<{ id: bigint; attachmentId: bigint }> {
    const m = await this.findOne(id);
    const oldAttachmentId = m.attachment_id;

    // 1. upload 新文件
    const newAttachmentId = await this.attachments.upload({
      fileData: input.fileData,
      filename: input.filename,
      bizType: 'case',
      bizId: m.case_id,
      category: input.category,
      contentType: input.contentType,
      uploadedBy: input.uploadedBy,
    });

    // 2. 更新指针；失败补偿删新附件
    try {
      const now = new Date();
      await this.prisma.$transaction(async (tx) => {
        await tx.case_material.update({
          where: { id },
          data: {
            attachment_id: newAttachmentId,
            updated_at: now,
            updated_by: input.uploadedBy,
          },
        });
      });
    } catch (e) {
      this.logger.warn(
        `更新 case_material 指针失败，补偿删新附件 ${newAttachmentId}: ${getErrorMessage(e)}`,
      );
      await this.attachments.delete(newAttachmentId, true).catch((err) => {
        this.logger.error(
          `补偿删新附件失败 ${newAttachmentId}: ${getErrorMessage(err)}`,
        );
      });
      throw e;
    }

    // 3. 成功后软删旧附件（若有）——新文件就绪前不破坏旧指针
    if (oldAttachmentId) {
      await this.attachments.delete(oldAttachmentId, true).catch((err) => {
        this.logger.warn(
          `旧附件清理失败 ${oldAttachmentId}: ${getErrorMessage(err)}`,
        );
      });
    }
    return { id, attachmentId: newAttachmentId };
  }

  /** 软删材料 + 级联软删附件 + 删 MinIO。 */
  async remove(id: bigint, operatorId: bigint): Promise<void> {
    const m = await this.findOne(id);
    const attachmentId = m.attachment_id;
    const now = new Date();

    await this.prisma.$transaction(async (tx) => {
      await tx.case_material.update({
        where: { id },
        data: { deleted_at: now, updated_at: now, updated_by: operatorId },
      });
    });

    if (attachmentId) {
      await this.attachments.delete(attachmentId, true).catch((err) => {
        this.logger.warn(
          `级联删附件失败 ${attachmentId}: ${getErrorMessage(err)}`,
        );
      });
    }
  }

  /** 便捷下载（透传 AttachmentService.getDownload）。 */
  async download(id: bigint) {
    const m = await this.findOne(id);
    if (!m.attachment_id) {
      throw new NotFoundException(`材料无电子附件: id=${id}`);
    }
    return this.attachments.getDownload(m.attachment_id);
  }
}
