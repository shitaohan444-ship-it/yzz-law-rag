import { PartialType } from '@nestjs/mapped-types';
import { IsIn, IsInt, IsOptional, Min } from 'class-validator';
import { CreateKnowledgeCategoryDto } from './create-knowledge-category.dto';

export class UpdateKnowledgeCategoryDto extends PartialType(
  CreateKnowledgeCategoryDto,
) {
  @IsOptional()
  @IsInt()
  @Min(0)
  sort_order?: number;

  @IsOptional()
  @IsIn(['active', 'inactive'])
  status?: 'active' | 'inactive';
}
