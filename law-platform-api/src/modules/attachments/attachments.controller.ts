import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Post,
  StreamableFile,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { ParseBigIntPipe } from '../../common/parse-bigint.pipe';
import { AttachmentService } from './attachment.service';
import { UploadAttachmentDto } from './dto/upload-attachment.dto';
import { BindAttachmentDto } from './dto/bind-attachment.dto';

/**
 * 附件 HTTP API（阶段 3）—— 对照方案 §7.2。
 *
 * @TODO 鉴权：uploadedBy 目前由请求参数传入，待鉴权体系建好后，
 *       全部改为 JwtAuthGuard 从 token 解析当前员工。
 */
@Controller('attachments')
export class AttachmentsController {
  constructor(private readonly attachments: AttachmentService) {}

  /** 上传文件到 MinIO + 写 sys_attachment（+可选 relation）。返回 attachment_id。 */
  @Post('upload')
  @UseInterceptors(
    FileInterceptor('file', {
      limits: { fileSize: 100 * 1024 * 1024 }, // 100MB
    }),
  )
  async upload(
    @UploadedFile() file: Express.Multer.File,
    @Body() dto: UploadAttachmentDto,
  ) {
    if (!file)
      throw new BadRequestException('缺少上传文件（表单字段名需为 file）');
    const id = await this.attachments.upload({
      fileData: file.buffer,
      filename: file.originalname,
      bizType: dto.bizType,
      bizId: BigInt(dto.bizId),
      category: dto.category,
      uploadedBy: BigInt(dto.uploadedBy),
      contentType: dto.contentType ?? file.mimetype,
      entityType: dto.entityType,
      entityId: dto.entityId != null ? BigInt(dto.entityId) : undefined,
      fileUsage: dto.fileUsage != null ? Number(dto.fileUsage) : undefined,
    });
    return { id }; // BigInt 经全局 toJSON 序列化为 string
  }

  /** 下载附件（流式返回）。 */
  @Get(':id/download')
  async download(
    @Param('id', ParseBigIntPipe) id: bigint,
  ): Promise<StreamableFile> {
    const payload = await this.attachments.getDownload(id);
    return new StreamableFile(payload.buffer, {
      type: payload.mimeType,
      disposition: `attachment; filename="${encodeURIComponent(payload.fileName)}"`,
    });
  }

  /** 生成预签名 URL（前端可凭此直连 MinIO 下载，默认 1h）。 */
  @Get(':id/presigned-url')
  async presignedUrl(
    @Param('id', ParseBigIntPipe) id: bigint,
  ): Promise<{ url: string }> {
    const url = await this.attachments.getPresignedUrl(id);
    return { url };
  }

  /** 软删附件（先提交 DB 软删 → 后删 MinIO）。 */
  @Delete(':id')
  async remove(
    @Param('id', ParseBigIntPipe) id: bigint,
  ): Promise<{ ok: true }> {
    await this.attachments.delete(id, true);
    return { ok: true };
  }

  /** 追加多态关联到 sys_attachment_relation。返回 relation_id。 */
  @Post(':id/bind')
  async bind(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: BindAttachmentDto,
  ): Promise<{ relationId: bigint }> {
    const relationId = await this.attachments.bind({
      attachmentId: id,
      entityType: dto.entityType,
      entityId: BigInt(dto.entityId),
      fileUsage: dto.fileUsage != null ? Number(dto.fileUsage) : null,
      isPrimary: dto.isPrimary != null ? Number(dto.isPrimary) : 0,
      operatorId: dto.operatorId != null ? BigInt(dto.operatorId) : null,
    });
    return { relationId };
  }
}
