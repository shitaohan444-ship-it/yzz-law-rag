import {
  ArrayMaxSize,
  ArrayMinSize,
  IsArray,
  IsObject,
  IsOptional,
  Matches,
  ValidateNested,
} from 'class-validator';

export class BatchRestoreDocumentsDto {
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(100)
  @Matches(/^[1-9]\d*$/, { each: true })
  doc_ids!: string[];

  /** 原分类已失效（停用/不可归档/被删）的文档，需在此指定新的可归档分类。 */
  @IsOptional()
  @IsObject()
  @ValidateNested()
  category_overrides?: Record<string, string>;
}
