import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Patch,
  Post,
  Query,
  StreamableFile,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { ParseBigIntPipe } from '../../common/parse-bigint.pipe';
import { CaseMaterialService } from './case-material.service';
import { CreateCaseMaterialDto } from './dto/create-case-material.dto';
import { UpdateCaseMaterialDto } from './dto/update-case-material.dto';
import { QueryCaseMaterialDto } from './dto/query-case-material.dto';
import { ReplaceFileDto } from './dto/replace-file.dto';

/**
 * 案件材料 HTTP API（案件附件集成）。
 * 单 Controller 空前缀，双路由前缀：
 *  - cases/:caseId/materials  （案件维度：建 / 列表）
 *  - case-materials/:id       （材料维度：详情 / 改 / 补文件 / 删 / 下载）
 *
 * @TODO 鉴权：uploadedBy / operatorId 现由请求参数传入，待鉴权体系建好换 JwtAuthGuard。
 */
@Controller()
export class CaseMaterialsController {
  constructor(private readonly materials: CaseMaterialService) {}

  /** 建材料：带文件（multipart）走 createWithFile，无文件（JSON）走 createRegistration。 */
  @Post('cases/:caseId/materials')
  @UseInterceptors(
    FileInterceptor('file', { limits: { fileSize: 100 * 1024 * 1024 } }),
  )
  async create(
    @Param('caseId', ParseBigIntPipe) caseId: bigint,
    @UploadedFile() file: Express.Multer.File | undefined,
    @Body() dto: CreateCaseMaterialDto,
  ) {
    if (file) {
      if (!dto.category) {
        throw new BadRequestException(
          '带文件上传时 category（MinIO 存储分类）必填',
        );
      }
      return this.materials.createWithFile({
        caseId,
        fileData: file.buffer,
        filename: file.originalname,
        contentType: file.mimetype,
        materialName: dto.materialName,
        materialType: dto.materialType,
        category: dto.category,
        sourceFrom: dto.sourceFrom,
        receivedAt: dto.receivedAt ? new Date(dto.receivedAt) : undefined,
        receivedBy: dto.receivedBy ? BigInt(dto.receivedBy) : undefined,
        uploadedBy: BigInt(dto.uploadedBy),
        remark: dto.remark,
      });
    }
    return this.materials.createRegistration({
      caseId,
      materialName: dto.materialName,
      materialType: dto.materialType,
      sourceFrom: dto.sourceFrom,
      receivedAt: dto.receivedAt ? new Date(dto.receivedAt) : undefined,
      receivedBy: dto.receivedBy ? BigInt(dto.receivedBy) : undefined,
      nasPath: dto.nasPath,
      uploadedBy: BigInt(dto.uploadedBy),
      remark: dto.remark,
    });
  }

  /** 案件下材料列表（分页 + 过滤 + 附件元信息）。 */
  @Get('cases/:caseId/materials')
  async list(
    @Param('caseId', ParseBigIntPipe) caseId: bigint,
    @Query() q: QueryCaseMaterialDto,
  ) {
    return this.materials.listByCase(caseId, {
      materialType: q.materialType,
      hasFile:
        q.hasFile === 'true' ? true : q.hasFile === 'false' ? false : undefined,
      reviewStatus: q.reviewStatus,
      page: q.page ?? 1,
      pageSize: q.pageSize ?? 20,
    });
  }

  /** 材料详情（含附件元信息）。 */
  @Get('case-materials/:id')
  async findOne(@Param('id', ParseBigIntPipe) id: bigint) {
    return this.materials.findOne(id);
  }

  /** 改材料元数据（不含文件）。 */
  @Patch('case-materials/:id')
  async update(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: UpdateCaseMaterialDto,
  ) {
    return this.materials.update(id, {
      materialName: dto.materialName,
      materialType: dto.materialType,
      sourceFrom: dto.sourceFrom,
      receivedAt: dto.receivedAt ? new Date(dto.receivedAt) : undefined,
      receivedBy: dto.receivedBy ? BigInt(dto.receivedBy) : undefined,
      remark: dto.remark,
      updatedBy: BigInt(dto.updatedBy),
    });
  }

  /** 后补/替换文件（multipart）。 */
  @Post('case-materials/:id/file')
  @UseInterceptors(
    FileInterceptor('file', { limits: { fileSize: 100 * 1024 * 1024 } }),
  )
  async replaceFile(
    @Param('id', ParseBigIntPipe) id: bigint,
    @UploadedFile() file: Express.Multer.File,
    @Body() dto: ReplaceFileDto,
  ) {
    if (!file) throw new BadRequestException('缺少上传文件');
    return this.materials.replaceFile(id, {
      fileData: file.buffer,
      filename: file.originalname,
      contentType: file.mimetype,
      category: dto.category,
      uploadedBy: BigInt(dto.uploadedBy),
    });
  }

  /** 软删材料 + 级联软删附件 + 删 MinIO。 */
  @Delete('case-materials/:id')
  async remove(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Query('operatorId') operatorId: string,
  ) {
    await this.materials.remove(id, BigInt(operatorId));
    return { ok: true };
  }

  /** 便捷下载（透传附件服务）。 */
  @Get('case-materials/:id/download')
  async download(
    @Param('id', ParseBigIntPipe) id: bigint,
  ): Promise<StreamableFile> {
    const payload = await this.materials.download(id);
    return new StreamableFile(payload.buffer, {
      type: payload.mimeType,
      disposition: `attachment; filename="${encodeURIComponent(payload.fileName)}"`,
    });
  }
}
