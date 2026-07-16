import {
  IsIn,
  IsNotEmpty,
  IsOptional,
  IsString,
  MaxLength,
} from 'class-validator';
import { ATTACHMENT_CATEGORIES } from '../../../common/attachment-categories';

/**
 * 建案件材料 DTO。兼容两种形态（controller 按 file 有无分流）：
 *  - 带文件（multipart）：materialName / materialType / category / uploadedBy 必填
 *  - 纯登记（JSON，无文件）：materialName / materialType 必填，可填 nasPath
 *
 * multipart 字段一律按 string 接收，controller 内转 BigInt / Date。
 *
 * 字典软绑定（无 FK，仅约定）：
 *  - materialType  → sys_dict_item.code_category = 'material_type'
 *  - sourceFrom    → sys_dict_item.code_category = 'material_source_from'
 *  - reviewStatus  → sys_dict_item.code_category = 'review_status'（service 默认 'pending'）
 */
export class CreateCaseMaterialDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  materialName: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(80)
  materialType: string; // 案件业务分类（软绑字典 material_type）

  /** MinIO 存储分类（决定 object_key 路径段）；仅带文件时有意义。与 materialType 是两个维度。 */
  @IsOptional()
  @IsIn(ATTACHMENT_CATEGORIES)
  category?: string;

  @IsOptional()
  @IsString()
  @MaxLength(120)
  sourceFrom?: string;

  @IsOptional()
  @IsString()
  receivedAt?: string; // ISO8601，controller new Date()

  @IsOptional()
  @IsString()
  receivedBy?: string; // 员工 ID，controller BigInt()

  @IsOptional()
  @IsString()
  @MaxLength(500)
  nasPath?: string; // 纯物理材料路径（无电子附件时填）

  @IsOptional()
  @IsString()
  @MaxLength(500)
  remark?: string;

  @IsString()
  @IsNotEmpty()
  uploadedBy: string; // 操作人员工 ID —— @TODO 鉴权后换 JwtAuthGuard
}
