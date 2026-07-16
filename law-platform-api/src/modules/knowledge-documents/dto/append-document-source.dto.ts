import { IsOptional, IsString, MaxLength } from 'class-validator';

export class AppendDocumentSourceDto {
  @IsOptional()
  @IsString()
  @MaxLength(255)
  source_title?: string;
}
