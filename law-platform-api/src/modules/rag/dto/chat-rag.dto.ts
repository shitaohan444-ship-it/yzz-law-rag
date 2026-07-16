import {
  ArrayMaxSize,
  IsArray,
  IsInt,
  IsOptional,
  IsString,
  Max,
  MaxLength,
  Min,
  MinLength,
} from 'class-validator';

export class ChatRagDto {
  @IsString()
  @MinLength(1)
  @MaxLength(4000)
  question!: string;

  @IsOptional()
  @IsString()
  @MinLength(1)
  @MaxLength(100)
  session_id?: string;

  @IsOptional()
  @IsInt()
  @Min(1)
  @Max(20)
  top_k?: number;

  @IsOptional()
  @IsArray()
  @ArrayMaxSize(200)
  @IsInt({ each: true })
  @Min(1, { each: true })
  doc_ids?: number[];

  @IsOptional()
  @IsInt()
  @Min(1)
  case_id?: number;
}
