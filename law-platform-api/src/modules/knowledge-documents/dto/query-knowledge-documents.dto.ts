import { Type } from 'class-transformer';
import {
  IsIn,
  IsInt,
  IsOptional,
  IsString,
  Max,
  MaxLength,
  Min,
} from 'class-validator';
import { KNOWLEDGE_CATEGORIES } from './create-knowledge-document.dto';
import type { KnowledgeCategory } from './create-knowledge-document.dto';

export class QueryKnowledgeDocumentsDto {
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page = 1;

  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(1000)
  page_size = 20;

  @IsOptional()
  @IsIn(KNOWLEDGE_CATEGORIES)
  category?: KnowledgeCategory;

  @IsOptional()
  @IsIn(['pending', 'processing', 'success', 'failed', 'skipped'])
  status?: string;

  @IsOptional()
  @IsString()
  @MaxLength(100)
  keyword?: string;
}
