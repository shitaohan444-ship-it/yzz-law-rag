import { Type } from 'class-transformer';
import {
  IsIn,
  IsInt,
  IsOptional,
  IsString,
  Max,
  MaxLength,
  Min,
  Matches,
} from 'class-validator';

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
  @Matches(/^[1-9]\d*$/)
  category_id?: string;

  @IsOptional()
  @IsIn(['pending', 'processing', 'success', 'failed', 'skipped'])
  status?: string;

  @IsOptional()
  @IsString()
  @MaxLength(100)
  keyword?: string;
}
