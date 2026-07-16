import { IsIn, IsString, MaxLength, MinLength } from 'class-validator';

export const KNOWLEDGE_CATEGORIES = ['法规', '案例', '工作资料'] as const;
export type KnowledgeCategory = (typeof KNOWLEDGE_CATEGORIES)[number];

export class CreateKnowledgeDocumentDto {
  @IsString()
  @MinLength(1)
  @MaxLength(255)
  title!: string;

  @IsIn(KNOWLEDGE_CATEGORIES)
  category!: KnowledgeCategory;
}
