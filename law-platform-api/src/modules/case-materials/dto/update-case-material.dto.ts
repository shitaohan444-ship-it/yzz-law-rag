import { OmitType, PartialType } from '@nestjs/mapped-types';
import { IsNotEmpty, IsString } from 'class-validator';
import { CreateCaseMaterialDto } from './create-case-material.dto';

/**
 * 改材料元数据（不含文件相关：category / uploadedBy / nasPath 走各自的端点）。
 */
export class UpdateCaseMaterialDto extends OmitType(
  PartialType(CreateCaseMaterialDto),
  ['category', 'uploadedBy', 'nasPath'],
) {
  @IsString()
  @IsNotEmpty()
  updatedBy: string; // 操作人员工 ID —— @TODO 鉴权
}
