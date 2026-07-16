import { Type } from 'class-transformer';
import { IsIn, IsInt, IsOptional, IsString, Min } from 'class-validator';

/**
 * 案件材料列表查询（GET query string）。
 */
export class QueryCaseMaterialDto {
  @IsOptional()
  @IsString()
  materialType?: string;

  /** 'true' = 仅有附件 / 'false' = 仅无附件 / 不传 = 全部 */
  @IsOptional()
  @IsIn(['true', 'false'])
  hasFile?: string;

  @IsOptional()
  @IsString()
  reviewStatus?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page?: number = 1;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  pageSize?: number = 20;
}
