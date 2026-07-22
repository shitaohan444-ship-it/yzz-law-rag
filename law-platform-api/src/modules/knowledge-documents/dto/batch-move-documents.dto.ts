import { ArrayMaxSize, ArrayMinSize, IsArray, Matches } from 'class-validator';

export class BatchMoveDocumentsDto {
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(100)
  @Matches(/^[1-9]\d*$/, { each: true })
  doc_ids!: string[];

  @Matches(/^[1-9]\d*$/)
  category_id!: string;
}
