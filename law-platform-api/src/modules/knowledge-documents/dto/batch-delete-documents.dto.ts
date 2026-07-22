import { ArrayMaxSize, ArrayMinSize, IsArray, Matches } from 'class-validator';

export class BatchDeleteDocumentsDto {
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(100)
  @Matches(/^[1-9]\d*$/, { each: true })
  doc_ids!: string[];
}
