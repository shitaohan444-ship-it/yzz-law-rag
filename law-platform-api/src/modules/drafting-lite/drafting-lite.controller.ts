import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Param,
  Post,
  Query,
  StreamableFile,
  UploadedFiles,
  UseInterceptors,
} from '@nestjs/common';
import { FilesInterceptor } from '@nestjs/platform-express';
import { DraftingLiteService } from './drafting-lite.service';
import { PartyRecord } from './drafting-lite.types';

const MAX_TOTAL_BYTES = 100 * 1024 * 1024;

function validateCauseShape(cause: string, allowAuto: boolean): void {
  if (
    (!allowAuto && cause === 'auto') ||
    !/^[a-z][a-z0-9_]{1,79}$/.test(cause)
  ) {
    throw new BadRequestException({
      code: 'DRAFTING_LITE_CAUSE_INVALID',
      message: allowAuto ? '案由选择无效' : '请选择一个支持的具体案由',
    });
  }
}

@Controller('api/drafting-lite')
export class DraftingLiteController {
  constructor(private readonly drafting: DraftingLiteService) {}

  @Get('causes')
  causes() {
    return this.drafting.listCauses();
  }

  @Get('materials')
  materials(
    @Query('keyword') keyword = '',
    @Query('page') page = '1',
    @Query('page_size') pageSize = '20',
    @Query('case_status') caseStatus = 'all',
  ) {
    return this.drafting.listMaterials({
      keyword,
      page: Number(page),
      pageSize: Number(pageSize),
      caseStatus,
    });
  }

  @Post('jobs')
  @UseInterceptors(
    FilesInterceptor('files', 10, {
      limits: { files: 10, fileSize: MAX_TOTAL_BYTES },
    }),
  )
  create(
    @UploadedFiles() files: Express.Multer.File[] | undefined,
    @Body('cause') cause = 'auto',
    @Body('knowledge_document_ids') knowledgeDocumentIdsRaw = '[]',
  ) {
    let knowledgeDocumentIds: string[];
    try {
      const parsed = JSON.parse(knowledgeDocumentIdsRaw) as unknown;
      if (!Array.isArray(parsed)) throw new Error('not an array');
      knowledgeDocumentIds = [...new Set(parsed.map(String))];
    } catch {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_KNOWLEDGE_IDS_INVALID',
        message: '知识库材料参数格式无效',
      });
    }
    const uploads = files ?? [];
    if (!uploads.length && !knowledgeDocumentIds.length) {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_MATERIALS_REQUIRED',
        message: '请至少选择或上传一份当事人材料',
      });
    }
    if (uploads.length + knowledgeDocumentIds.length > 10) {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_MATERIALS_LIMIT',
        message: '一次任务最多选择10份材料',
      });
    }
    if (uploads.reduce((total, file) => total + file.size, 0) > MAX_TOTAL_BYTES) {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_FILES_TOO_LARGE',
        message: '上传文件总大小不能超过100MB',
      });
    }
    validateCauseShape(cause, true);
    return this.drafting.create(uploads, cause, knowledgeDocumentIds);
  }

  @Get('jobs/:jobId')
  get(@Param('jobId') jobId: string) {
    return this.drafting.get(jobId);
  }

  @Post('jobs/:jobId/cancel')
  cancel(@Param('jobId') jobId: string) {
    return this.drafting.cancel(jobId);
  }

  @Post('jobs/:jobId/cause')
  selectCause(
    @Param('jobId') jobId: string,
    @Body('cause') cause: string,
  ) {
    validateCauseShape(cause, false);
    return this.drafting.selectCause(jobId, cause);
  }

  @Post('jobs/:jobId/parties')
  confirmParties(
    @Param('jobId') jobId: string,
    @Body()
    body: { version: number; parties: PartyRecord[]; confirmed: boolean },
  ) {
    if (
      !Number.isInteger(body.version) ||
      body.version < 0 ||
      !Array.isArray(body.parties) ||
      body.parties.length > 100 ||
      body.confirmed !== true
    ) {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_PARTIES_INVALID',
        message: '当事人确认参数无效',
      });
    }
    return this.drafting.confirmParties(jobId, body);
  }

  @Get('jobs/:jobId/download')
  async download(@Param('jobId') jobId: string) {
    const result = await this.drafting.download(jobId);
    return new StreamableFile(result.body, {
      type: result.contentType,
      disposition: result.disposition,
    });
  }

  @Get('jobs/:jobId/artifacts/:artifactType/download')
  async downloadArtifact(
    @Param('jobId') jobId: string,
    @Param('artifactType') artifactType: string,
  ) {
    if (
      artifactType !== 'complaint' &&
      artifactType !== 'evidence_directory' &&
      artifactType !== 'evidence_package'
    ) {
      throw new BadRequestException({
        code: 'DRAFTING_LITE_ARTIFACT_INVALID',
        message: '文书产物类型无效',
      });
    }
    const result = await this.drafting.downloadArtifact(jobId, artifactType);
    return new StreamableFile(result.body, {
      type: result.contentType,
      disposition: result.disposition,
    });
  }
}
