import { IsNotEmpty, IsOptional, IsString } from 'class-validator';

/**
 * 追加附件多态关联 DTO（JSON body）。
 * id 字段一律按 string 接收（避免 bigint 超 Number.MAX_SAFE_INTEGER），controller 内转 BigInt。
 */
export class BindAttachmentDto {
  @IsString()
  @IsNotEmpty()
  entityType: string; // party/lead/client/case/contract/invoice/document

  @IsString()
  @IsNotEmpty()
  entityId: string;

  @IsOptional()
  @IsString()
  fileUsage?: string; // attachment_usage 字典值

  @IsOptional()
  @IsString()
  isPrimary?: string; // '0'/'1'

  @IsOptional()
  @IsString()
  operatorId?: string; // 操作人员工 ID
}
