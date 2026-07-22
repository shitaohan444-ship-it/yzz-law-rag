import { Matches } from 'class-validator';

export class UpdateDocumentCategoryDto {
  @Matches(/^[1-9]\d*$/)
  category_id!: string;
}
