import {
  IsIn,
  IsInt,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
  Max,
  MaxLength,
  Min,
} from 'class-validator';
import { GENERATION_RUN_STATUSES } from '../legal-drafting.types';

export class ClaimRunDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(120)
  worker_id: string;

  @IsOptional()
  @IsInt()
  @Min(30)
  @Max(600)
  lease_seconds?: number;
}

export class HeartbeatDto extends ClaimRunDto {
  @IsInt()
  @Min(0)
  event_seq: number;
}

export class WorkerEventDto {
  @IsInt()
  @Min(1)
  event_seq: number;

  @IsString()
  @IsNotEmpty()
  @MaxLength(60)
  event_type: string;

  @IsOptional()
  @IsIn(GENERATION_RUN_STATUSES)
  status?: (typeof GENERATION_RUN_STATUSES)[number];

  @IsOptional()
  @IsString()
  @MaxLength(100)
  current_node?: string;

  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(100)
  progress?: number;

  @IsOptional()
  @IsObject()
  payload?: Record<string, unknown>;

  @IsOptional()
  @IsString()
  @MaxLength(80)
  error_code?: string;

  @IsOptional()
  @IsString()
  @MaxLength(4000)
  error_message?: string;
}
