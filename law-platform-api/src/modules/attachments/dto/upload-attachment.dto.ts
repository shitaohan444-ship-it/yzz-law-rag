import { IsIn, IsNotEmpty, IsOptional, IsString } from 'class-validator';

/** 附件业务分类（与 MinioService.CATEGORIES 对齐） */
const CATEGORIES = [
  'evidence',
  'contract',
  'pleading',
  'court',
  'progress',
  'consultation',
  'invoice',
  'agreement',
  'other',
] as const;

/**
 * 上传附件 DTO（multipart/form-data）。
 * file 字段通过 @UploadedFile() 取，DTO 只描述表单文本字段。
 * multipart 字段一律按 string 接收，controller 内转 BigInt/Number。
 */
export class UploadAttachmentDto {
  @IsString()
  @IsNotEmpty()
  bizType: string; // case/lead/fee_agreement/...

  @IsString()
  @IsNotEmpty()
  bizId: string; // 业务对象 ID

  @IsString()
  @IsIn(CATEGORIES)
  category: string;

  @IsString()
  @IsNotEmpty()
  uploadedBy: string; // 上传人员工 ID —— @TODO 鉴权体系建好后换 JwtAuthGuard 从 token 解析

  @IsOptional()
  @IsString()
  contentType?: string;

  @IsOptional()
  @IsString()
  entityType?: string; // 提供则同步写 sys_attachment_relation

  @IsOptional()
  @IsString()
  entityId?: string;

  @IsOptional()
  @IsString()
  fileUsage?: string; // attachment_usage 字典值
}
