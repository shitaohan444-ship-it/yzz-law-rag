import { Injectable, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Client } from 'minio';
import { Readable } from 'stream';
import { randomUUID } from 'crypto';

/**
 * MinIO 基础文件服务 —— 对照 Python `law-rag-service/app/services/minio_service.py`。
 * 只负责对象存储通用 CRUD 与 object_key 生成规则，不绑定数据库表。
 *
 * 与 Python 的关键差异（JS minio SDK v8）：
 * - putObject 返回值跨版本不稳定 → 上传后再 statObject 取权威 etag / size
 * - getObject 返回 Readable 流 → 需 streamToBuffer
 * - statObject 不存在时错误形态：err.code==='NoSuchKey' 或 err.statusCode===404，二者都判
 */
@Injectable()
export class MinioService implements OnModuleInit {
  /** 业务分类（与数据库字段解耦，上层按业务语义选用） */
  static readonly CATEGORIES = new Set<string>([
    'evidence', // 证据
    'contract', // 合同
    'pleading', // 诉状/答辩状等法律文书
    'court', // 开庭/法院相关材料
    'progress', // 办案进展材料
    'consultation', // 咨询记录
    'invoice', // 发票/收据
    'agreement', // 协议
    'other', // 其他
  ]);

  private client!: Client;
  private bucketName!: string;

  constructor(private readonly config: ConfigService) {}

  onModuleInit(): void {
    this.bucketName =
      this.config.get<string>('MINIO_BUCKET') ?? 'law-firm-files';
    this.client = new Client({
      endPoint: this.config.get<string>('MINIO_ENDPOINT')!,
      port: this.config.get<number>('MINIO_PORT') ?? 9000,
      useSSL: this.config.get<boolean>('MINIO_USE_SSL') ?? false,
      accessKey: this.config.get<string>('MINIO_ACCESS_KEY')!,
      secretKey: this.config.get<string>('MINIO_SECRET_KEY')!,
    });
  }

  // ------------------------------------------------------------------
  // Bucket
  // ------------------------------------------------------------------
  async ensureBucket(bucket: string = this.bucketName): Promise<string> {
    if (!(await this.client.bucketExists(bucket))) {
      await this.client.makeBucket(bucket);
    }
    return bucket;
  }

  // ------------------------------------------------------------------
  // object_key 规则（与数据库字段解耦，只接受通用参数）
  // ------------------------------------------------------------------
  /**
   * 按规则生成 object_key（与 Python 逐字节一致）：
   *   常规：{prefix}/{year}/{mm}/{entityNo}/{category}/{yyyyMMddHHmmss}_{uuid8}_{filename}
   *   临时：temp/{yyyyMMdd}/{uuid8}_{filename}
   * 时间一律用 UTC（对齐 Python datetime.now(timezone.utc)）。
   */
  static buildObjectKey(
    prefix: string,
    opts: {
      filename: string;
      year?: number;
      month?: number;
      entityNo?: string;
      category?: string;
      temp?: boolean;
    },
  ): string {
    const { filename, year, month, entityNo, category, temp } = opts;

    if (temp) {
      return `temp/${MinioService.utcDate()}/${MinioService.uuid8()}_${filename}`;
    }

    if (year == null || month == null) {
      throw new Error('非 temp 模式下 year 和 month 必须提供');
    }
    if (!entityNo) throw new Error('非 temp 模式下 entity_no 必须提供');
    if (!category) throw new Error('非 temp 模式下 category 必须提供');
    if (!MinioService.CATEGORIES.has(category)) {
      throw new Error(
        `category 必须是 ${[...MinioService.CATEGORIES].sort().join('/')} 之一，收到: ${category}`,
      );
    }

    const mm = String(month).padStart(2, '0');
    return `${prefix}/${year}/${mm}/${entityNo}/${category}/${MinioService.utcTimestamp()}_${MinioService.uuid8()}_${filename}`;
  }

  // ------------------------------------------------------------------
  // Upload / Download / Presigned URL / Delete / Exists
  // ------------------------------------------------------------------
  /** 上传 bytes 到 MinIO，默认禁止覆盖；返回 bucket/object_key/etag/size。 */
  async uploadFile(
    objectKey: string,
    data: Buffer,
    opts: { contentType?: string; bucket?: string; overwrite?: boolean } = {},
  ): Promise<{
    bucket: string;
    objectKey: string;
    etag: string;
    size: number;
  }> {
    const bucket = opts.bucket ?? this.bucketName;
    await this.ensureBucket(bucket);

    if (!opts.overwrite && (await this.fileExists(objectKey, bucket))) {
      throw new Error(
        `对象已存在，禁止覆盖: bucket=${bucket}, object_key=${objectKey}`,
      );
    }

    const contentType =
      opts.contentType ??
      MinioService.guessContentType(objectKey) ??
      'application/octet-stream';

    await this.client.putObject(bucket, objectKey, data, data.length, {
      'Content-Type': contentType,
    });

    // JS SDK putObject 返回的 etag 跨版本不稳定 → 用 statObject 取权威值
    const stat = await this.client.statObject(bucket, objectKey);
    return {
      bucket,
      objectKey,
      etag: stat.etag,
      size: Number(stat.size),
    };
  }

  /** 下载对象，返回 Buffer。 */
  async downloadFile(objectKey: string, bucket?: string): Promise<Buffer> {
    const stream = await this.client.getObject(
      bucket ?? this.bucketName,
      objectKey,
    );
    return this.streamToBuffer(stream);
  }

  /** 生成预签名 URL。 */
  async getPresignedUrl(
    objectKey: string,
    opts: { expires?: number; method?: 'GET' | 'PUT'; bucket?: string } = {},
  ): Promise<string> {
    const bucket = opts.bucket ?? this.bucketName;
    const method = opts.method ?? 'GET';
    const expires = opts.expires ?? 3600;
    if (method === 'GET') {
      return this.client.presignedGetObject(bucket, objectKey, expires);
    }
    if (method === 'PUT') {
      return this.client.presignedPutObject(bucket, objectKey, expires);
    }
    throw new Error('不支持的预签名方法');
  }

  /** 删除对象（S3 删除不存在的对象幂等，不抛错）。 */
  async deleteFile(objectKey: string, bucket?: string): Promise<void> {
    await this.client.removeObject(bucket ?? this.bucketName, objectKey);
  }

  /** 检查对象是否存在。 */
  async fileExists(objectKey: string, bucket?: string): Promise<boolean> {
    try {
      await this.client.statObject(bucket ?? this.bucketName, objectKey);
      return true;
    } catch (e) {
      // minio statObject 对不存在对象抛 S3Error；响应形态随版本/请求类型（HEAD 无 body）而异，
      // 可能体现在 code='NoSuchKey'/'NotFound'、statusCode/status=404、或 message 含 'Not Found'
      const err = e as {
        code?: unknown;
        statusCode?: unknown;
        status?: unknown;
        message?: string;
      };
      const code = typeof err.code === 'string' ? err.code : '';
      const rawStatus = err.statusCode ?? err.status;
      const status =
        typeof rawStatus === 'number'
          ? rawStatus
          : typeof rawStatus === 'string'
            ? Number(rawStatus)
            : 0;
      if (
        code === 'NoSuchKey' ||
        code === 'NotFound' ||
        status === 404 ||
        /not found|nosuchkey/i.test(err?.message ?? '')
      ) {
        return false;
      }
      throw e;
    }
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  /** 根据文件名/对象键后缀猜测 MIME 类型（对照 Python _guess_content_type）。 */
  static guessContentType(filenameOrKey: string): string | undefined {
    const lower = filenameOrKey.toLowerCase();
    const map: Record<string, string> = {
      '.pdf': 'application/pdf',
      '.doc': 'application/msword',
      '.docx':
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      '.xls': 'application/vnd.ms-excel',
      '.xlsx':
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      '.ppt': 'application/vnd.ms-powerpoint',
      '.pptx':
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      '.txt': 'text/plain',
      '.md': 'text/markdown',
      '.png': 'image/png',
      '.jpg': 'image/jpeg',
      '.jpeg': 'image/jpeg',
      '.gif': 'image/gif',
      '.zip': 'application/zip',
    };
    for (const ext of Object.keys(map)) {
      if (lower.endsWith(ext)) return map[ext];
    }
    return undefined;
  }

  private static uuid8(): string {
    return randomUUID().replace(/-/g, '').slice(0, 8);
  }

  private static utcTimestamp(): string {
    const d = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}`;
  }

  private static utcDate(): string {
    const d = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}`;
  }

  private async streamToBuffer(stream: Readable): Promise<Buffer> {
    const chunks: Buffer[] = [];
    for await (const chunk of stream as AsyncIterable<unknown>) {
      if (typeof chunk === 'string' || chunk instanceof Uint8Array) {
        chunks.push(Buffer.from(chunk));
        continue;
      }
      throw new TypeError(
        'MinIO download stream returned an unsupported chunk',
      );
    }
    return Buffer.concat(chunks);
  }
}
