import { IsString, Matches, MaxLength, MinLength } from 'class-validator';

export class CreateKnowledgeDocumentDto {
  @IsString()
  @MinLength(1)
  @MaxLength(255)
  title!: string;

  @Matches(/^[1-9]\d*$/)
  category_id!: string;
}
