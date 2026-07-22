import { Transform, TransformFnParams } from 'class-transformer';
import {
  ArrayMaxSize,
  IsArray,
  IsBoolean,
  IsOptional,
  IsString,
  Matches,
  MaxLength,
  MinLength,
} from 'class-validator';

function normalizeAliases(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return (value as unknown[]).map((item: unknown) =>
    typeof item === 'string' ? item.trim() : item,
  );
}

export class CreateKnowledgeCategoryDto {
  @IsString()
  @MinLength(1)
  @MaxLength(120)
  name!: string;

  @IsOptional()
  @IsArray()
  @ArrayMaxSize(10)
  @IsString({ each: true })
  @MaxLength(50, { each: true })
  @Transform(({ value }: TransformFnParams) => normalizeAliases(value))
  aliases?: string[];

  @IsOptional()
  @Matches(/^[1-9]\d*$/)
  parent_id?: string | null;

  @IsOptional()
  @IsBoolean()
  assignable?: boolean;

  @IsOptional()
  @IsBoolean()
  sensitive?: boolean;
}
