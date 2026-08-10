import { Type } from 'class-transformer';
import {
  Allow,
  ArrayMinSize,
  ArrayMaxSize,
  IsArray,
  IsIn,
  IsInt,
  IsNotEmpty,
  IsOptional,
  IsString,
  MaxLength,
  IsBoolean,
  Min,
  ValidateNested,
} from 'class-validator';

export class CreateGenerationDto {
  @IsString()
  @IsNotEmpty()
  case_id: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(80)
  document_type: string;

  @IsOptional()
  @IsString()
  @MaxLength(80)
  cause_code?: string;

  @IsOptional()
  @IsString()
  @MaxLength(50)
  party_role?: string;

  @IsOptional()
  @IsString()
  template_version_id?: string;

  @IsArray()
  @ArrayMaxSize(200)
  @IsString({ each: true })
  material_ids: string[] = [];

  @IsArray()
  @ArrayMaxSize(500)
  @IsString({ each: true })
  evidence_ids: string[] = [];

  @IsArray()
  @ArrayMaxSize(200)
  @IsString({ each: true })
  knowledge_document_ids: string[] = [];

  @IsString()
  @IsNotEmpty()
  actor_id: string;

  @IsBoolean()
  fixed_identity: boolean = true;

  @IsOptional()
  @IsString()
  @MaxLength(120)
  idempotency_key?: string;
}

export class ConfirmTemplateDto {
  @IsString()
  @IsNotEmpty()
  template_version_id: string;

  @IsString()
  @IsNotEmpty()
  actor_id: string;
}

export class UserInputItemDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(160)
  field_id: string;

  @Allow()
  value: unknown;

  @IsIn(['confirmed', 'not_applicable', 'unable_to_confirm'])
  resolution_type: 'confirmed' | 'not_applicable' | 'unable_to_confirm';

  @IsOptional()
  @IsString()
  @MaxLength(500)
  source_note?: string;
}

export class SubmitUserInputsDto {
  @Type(() => Number)
  @IsInt()
  @Min(1)
  input_version: number;

  @IsArray()
  @ArrayMinSize(1)
  @ValidateNested({ each: true })
  @Type(() => UserInputItemDto)
  inputs: UserInputItemDto[];

  @IsString()
  @IsNotEmpty()
  actor_id: string;
}

export class ActorDto {
  @IsString()
  @IsNotEmpty()
  actor_id: string;
}

export class ReviewVersionDto extends ActorDto {
  @IsIn(['approved', 'returned'])
  action: 'approved' | 'returned';

  @IsOptional()
  @IsString()
  @MaxLength(2000)
  comment?: string;
}
