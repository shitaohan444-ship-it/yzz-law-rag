import {
  Body,
  Controller,
  Get,
  Headers,
  Param,
  Post,
  Query,
  StreamableFile,
  UploadedFiles,
  UseInterceptors,
} from '@nestjs/common';
import { FileFieldsInterceptor } from '@nestjs/platform-express';
import { ParseBigIntPipe } from '../../common/parse-bigint.pipe';
import { AttachmentService } from '../attachments/attachment.service';
import {
  ActorDto,
  ConfirmTemplateDto,
  CreateGenerationDto,
  ReviewVersionDto,
  SubmitUserInputsDto,
} from './dto/create-generation.dto';
import { ClaimRunDto, HeartbeatDto, WorkerEventDto } from './dto/worker.dto';
import { LegalDraftingService } from './legal-drafting.service';

@Controller('api')
export class LegalDraftingController {
  constructor(private readonly drafting: LegalDraftingService) {}

  @Get('legal-document-templates/matches')
  matchTemplates(
    @Query('document_type') documentType?: string,
    @Query('cause_code') causeCode?: string,
    @Query('party_role') partyRole?: string,
  ) {
    return this.drafting.matchTemplates({ documentType, causeCode, partyRole });
  }

  @Post('legal-document-generations')
  create(@Body() dto: CreateGenerationDto) {
    return this.drafting.createGeneration(dto);
  }

  @Get('legal-document-generations/:id')
  get(@Param('id', ParseBigIntPipe) id: bigint) {
    return this.drafting.getGeneration(id);
  }

  @Post('legal-document-generations/:id/template-confirmation')
  confirmTemplate(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: ConfirmTemplateDto,
  ) {
    return this.drafting.confirmTemplate(id, dto);
  }

  @Post('legal-document-generations/:id/inputs')
  submitInputs(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: SubmitUserInputsDto,
  ) {
    return this.drafting.submitInputs(id, dto);
  }

  @Post('legal-document-generations/:id/resume')
  resume(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: ActorDto,
  ) {
    return this.drafting.resume(id, dto);
  }

  @Post('legal-document-generations/:id/cancel')
  cancel(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: ActorDto,
  ) {
    return this.drafting.cancel(id, dto);
  }

  @Get('legal-documents/:id/versions')
  versions(@Param('id', ParseBigIntPipe) id: bigint) {
    return this.drafting.listVersions(id);
  }

  @Post('legal-documents/:id/versions/:versionId/review')
  reviewVersion(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Param('versionId', ParseBigIntPipe) versionId: bigint,
    @Body() dto: ReviewVersionDto,
  ) {
    return this.drafting.reviewVersion(id, versionId, dto);
  }
}

@Controller('internal/legal-drafting')
export class LegalDraftingWorkerController {
  constructor(
    private readonly drafting: LegalDraftingService,
    private readonly attachments: AttachmentService,
  ) {}

  private authorize(token?: string) {
    this.drafting.assertWorkerToken(token);
  }

  @Post('claims')
  claim(
    @Headers('x-legal-worker-token') token: string | undefined,
    @Body() dto: ClaimRunDto,
  ) {
    this.authorize(token);
    return this.drafting.claimRun(dto);
  }

  @Post('runs/:id/heartbeat')
  heartbeat(
    @Headers('x-legal-worker-token') token: string | undefined,
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: HeartbeatDto,
  ) {
    this.authorize(token);
    return this.drafting.heartbeat(id, dto);
  }

  @Get('runs/:id/case-snapshot')
  snapshot(
    @Headers('x-legal-worker-token') workerToken: string | undefined,
    @Headers('x-legal-run-token') runToken: string,
    @Param('id', ParseBigIntPipe) id: bigint,
  ) {
    this.authorize(workerToken);
    return this.drafting.getCaseSnapshot(id, runToken);
  }

  @Get('runs/:id/materials/:materialId/content')
  async materialContent(
    @Headers('x-legal-worker-token') workerToken: string | undefined,
    @Headers('x-legal-run-token') runToken: string,
    @Param('id', ParseBigIntPipe) id: bigint,
    @Param('materialId', ParseBigIntPipe) materialId: bigint,
  ): Promise<StreamableFile> {
    this.authorize(workerToken);
    const attachmentId = await this.drafting.authorizeMaterial(
      id,
      materialId,
      runToken,
    );
    const payload = await this.attachments.getDownload(attachmentId);
    return new StreamableFile(payload.buffer, {
      type: payload.mimeType,
      disposition: `attachment; filename="${encodeURIComponent(payload.fileName)}"`,
    });
  }

  @Post('runs/:id/artifacts')
  @UseInterceptors(
    FileFieldsInterceptor(
      [
        { name: 'docx', maxCount: 1 },
        { name: 'pdf', maxCount: 1 },
      ],
      { limits: { fileSize: 50 * 1024 * 1024 } },
    ),
  )
  persistArtifacts(
    @Headers('x-legal-worker-token') workerToken: string | undefined,
    @Headers('x-legal-run-token') runToken: string,
    @Param('id', ParseBigIntPipe) id: bigint,
    @UploadedFiles()
    files: {
      docx?: Express.Multer.File[];
      pdf?: Express.Multer.File[];
    },
    @Body('metadata') metadata: string,
  ) {
    this.authorize(workerToken);
    return this.drafting.persistArtifacts(id, runToken, files, metadata);
  }

  @Post('runs/:id/events')
  event(
    @Headers('x-legal-worker-token') token: string | undefined,
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: WorkerEventDto,
  ) {
    this.authorize(token);
    return this.drafting.recordEvent(id, dto);
  }
}
