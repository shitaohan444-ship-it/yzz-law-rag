import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Param,
  Patch,
  Post,
  Put,
  Query,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { ParseBigIntPipe } from '../../common/parse-bigint.pipe';
import { RagService } from '../rag/rag.service';
import { CreateKnowledgeDocumentDto } from './dto/create-knowledge-document.dto';
import { AppendDocumentSourceDto } from './dto/append-document-source.dto';
import { QueryKnowledgeDocumentsDto } from './dto/query-knowledge-documents.dto';
import { QueryTrashDocumentsDto } from './dto/query-trash-documents.dto';
import { QueryDocumentChunksDto } from './dto/query-document-chunks.dto';
import { KnowledgeDocumentsService } from './knowledge-documents.service';
import { UpdateDocumentCategoryDto } from './dto/update-document-category.dto';
import { BatchMoveDocumentsDto } from './dto/batch-move-documents.dto';
import { BatchDeleteDocumentsDto } from './dto/batch-delete-documents.dto';
import { BatchRestoreDocumentsDto } from './dto/batch-restore-documents.dto';
import { BatchPurgeDocumentsDto } from './dto/batch-purge-documents.dto';
import { UpdateDocumentTitleDto } from './dto/update-document-title.dto';

@Controller('api/rag/documents')
export class KnowledgeDocumentsController {
  constructor(
    private readonly documents: KnowledgeDocumentsService,
    private readonly rag: RagService,
  ) {}

  @Post()
  @UseInterceptors(
    FileInterceptor('file', { limits: { fileSize: 50 * 1024 * 1024 } }),
  )
  upload(
    @UploadedFile() file: Express.Multer.File | undefined,
    @Body() dto: CreateKnowledgeDocumentDto,
  ) {
    if (!file) throw new BadRequestException('请选择要上传的文件');
    return this.documents.create(file, dto);
  }

  @Post('batch-move')
  batchMove(@Body() dto: BatchMoveDocumentsDto) {
    return this.documents.batchMove(dto);
  }

  @Post('batch-delete')
  batchDelete(@Body() dto: BatchDeleteDocumentsDto) {
    return this.documents.batchDelete(dto);
  }

  @Post('batch-restore')
  batchRestore(@Body() dto: BatchRestoreDocumentsDto) {
    return this.documents.batchRestore(dto);
  }

  @Post('batch-purge')
  batchPurge(@Body() dto: BatchPurgeDocumentsDto) {
    return this.documents.batchPurge(dto);
  }

  @Put(':id/file')
  @UseInterceptors(
    FileInterceptor('file', { limits: { fileSize: 50 * 1024 * 1024 } }),
  )
  replaceFile(
    @Param('id', ParseBigIntPipe) id: bigint,
    @UploadedFile() file: Express.Multer.File | undefined,
    @Body() dto: CreateKnowledgeDocumentDto,
  ) {
    this.assertPositiveId(id);
    if (!file) throw new BadRequestException('请选择新的文档文件');
    return this.documents.replace(id, file, dto);
  }

  @Get()
  list(@Query() query: QueryKnowledgeDocumentsDto) {
    return this.documents.list(query);
  }

  @Get('trash')
  listTrash(@Query() query: QueryTrashDocumentsDto) {
    return this.documents.listTrash(query);
  }

  @Get(':id/sources')
  async sources(@Param('id', ParseBigIntPipe) id: bigint) {
    this.assertPositiveId(id);
    await this.documents.assertActiveDocument(id);
    return this.documents.listSources(id);
  }

  @Patch(':id/category')
  updateCategory(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: UpdateDocumentCategoryDto,
  ) {
    this.assertPositiveId(id);
    return this.documents.updateCategory(id, dto);
  }

  @Patch(':id/title')
  updateTitle(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: UpdateDocumentTitleDto,
  ) {
    this.assertPositiveId(id);
    return this.documents.updateTitle(id, dto);
  }

  @Post(':id/sources')
  @UseInterceptors(
    FileInterceptor('file', { limits: { fileSize: 50 * 1024 * 1024 } }),
  )
  appendSource(
    @Param('id', ParseBigIntPipe) id: bigint,
    @UploadedFile() file: Express.Multer.File | undefined,
    @Body() dto: AppendDocumentSourceDto,
  ) {
    this.assertPositiveId(id);
    if (!file) throw new BadRequestException('请选择要追加的文件');
    return this.documents.appendSource(id, file, dto);
  }

  @Put(':id/sources/:sourceId/file')
  @UseInterceptors(
    FileInterceptor('file', { limits: { fileSize: 50 * 1024 * 1024 } }),
  )
  replaceSource(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Param('sourceId', ParseBigIntPipe) sourceId: bigint,
    @UploadedFile() file: Express.Multer.File | undefined,
    @Body() dto: AppendDocumentSourceDto,
  ) {
    this.assertPositiveId(id);
    this.assertPositiveId(sourceId);
    if (!file) throw new BadRequestException('请选择新的源文件');
    return this.documents.replaceSource(id, sourceId, file, dto);
  }

  @Post(':id/ingest')
  async ingest(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Query('force') force?: string,
    @Query('generate_description') generateDescription?: string,
    @Query('analyze_images') analyzeImages?: string,
  ) {
    this.assertPositiveId(id);
    await this.documents.assertActiveDocument(id);
    if (force !== undefined && force !== 'true' && force !== 'false') {
      throw new BadRequestException('force 只能为 true 或 false');
    }
    for (const [name, value] of [
      ['generate_description', generateDescription],
      ['analyze_images', analyzeImages],
    ] as const) {
      if (value !== undefined && value !== 'true' && value !== 'false') {
        throw new BadRequestException(`${name} 只能为 true 或 false`);
      }
    }
    if (force === 'true') {
      return this.documents.rebuildSources(id);
    }
    return this.rag.ingestDocument(id.toString(), false, {
      ...(generateDescription !== undefined && {
        generateDescription: generateDescription === 'true',
      }),
      ...(analyzeImages !== undefined && {
        analyzeImages: analyzeImages === 'true',
      }),
    });
  }

  @Get(':id/status')
  async status(@Param('id', ParseBigIntPipe) id: bigint) {
    this.assertPositiveId(id);
    await this.documents.assertActiveDocument(id);
    return this.rag.getDocumentStatus(id.toString());
  }

  @Get(':id/markdown')
  async markdown(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Query('source_id') sourceId?: string,
  ) {
    this.assertPositiveId(id);
    await this.documents.assertActiveDocument(id);
    return this.rag.getDocumentMarkdown(
      id.toString(),
      this.optionalPositiveId(sourceId),
    );
  }

  @Get(':id/chunks')
  async chunks(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Query() query: QueryDocumentChunksDto,
  ) {
    this.assertPositiveId(id);
    await this.documents.assertActiveDocument(id);
    return this.rag.getDocumentChunks(
      id.toString(),
      query.page,
      query.page_size,
      query.source_id?.toString(),
    );
  }

  private assertPositiveId(id: bigint): void {
    if (id <= 0) throw new BadRequestException('文档 ID 必须为正整数');
  }

  private optionalPositiveId(value?: string): string | undefined {
    if (value === undefined) return undefined;
    if (!/^[1-9]\d*$/.test(value)) {
      throw new BadRequestException('source_id 必须为正整数');
    }
    return value;
  }
}
