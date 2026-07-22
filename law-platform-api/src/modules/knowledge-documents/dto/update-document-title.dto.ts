import { Transform, TransformFnParams } from 'class-transformer';
import { IsString, MaxLength, MinLength } from 'class-validator';

export class UpdateDocumentTitleDto {
  @Transform((params: TransformFnParams) => {
    const value: unknown = params.value;
    return typeof value === 'string' ? value.trim() : value;
  })
  @IsString()
  @MinLength(1)
  @MaxLength(255)
  title!: string;
}
