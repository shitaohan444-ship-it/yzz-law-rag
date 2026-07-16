/**
 * 附件 HTTP API 端到端验证（阶段 3）。
 * 用 supertest 跑真实 HTTP：upload(multipart) → presigned-url → download → delete。
 * 连真实 PG + 真实 MinIO，固定文件名保证幂等。
 */
import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import request from 'supertest';
import { AppModule } from '../src/app.module';
import { PrismaService } from '../src/core/prisma/prisma.service';
import { MinioService } from '../src/core/minio/minio.service';
import type { Server } from 'node:http';

const CONTENT = Buffer.from('http e2e 附件上传测试', 'utf8');
const FILENAME = '_http_probe.pdf';

// 二进制响应解析（supertest 默认按文本，会损坏字节）
const binaryParse = (
  res: { on: (e: string, cb: (c: Buffer) => void) => void },
  cb: (e: unknown, body: Buffer) => void,
) => {
  const chunks: Buffer[] = [];
  res.on('data', (c: Buffer) => chunks.push(c));
  res.on('end', () => cb(null, Buffer.concat(chunks)));
};

describe('Attachments HTTP (e2e)', () => {
  let app: INestApplication;
  let server: Server;
  let prisma: PrismaService;
  let minio: MinioService;
  let caseId: bigint;
  let uploader: bigint;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
    app = moduleFixture.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({ whitelist: true, transform: true }),
    );
    // 与 main.ts 一致：BigInt 序列化为 string
    (BigInt.prototype as unknown as { toJSON: () => string }).toJSON =
      function () {
        return String(this);
      };
    await app.init();
    server = app.getHttpServer() as Server;

    prisma = app.get(PrismaService);
    minio = app.get(MinioService);

    // cleanup（幂等）：清掉上次 http probe 残留
    const stale = await prisma.$queryRaw<
      { id: bigint; object_key: string | null; storage_path: string }[]
    >`SELECT id, object_key, storage_path FROM oa.sys_attachment WHERE file_name = ${FILENAME}`;
    for (const row of stale) {
      await prisma.$executeRaw`DELETE FROM oa.sys_attachment_relation WHERE attachment_id = ${row.id}`.catch(
        () => {},
      );
      const ok = row.object_key ?? row.storage_path;
      if (ok) await minio.deleteFile(ok).catch(() => {});
      await prisma.$executeRaw`DELETE FROM oa.sys_attachment WHERE id = ${row.id}`;
    }

    // 种子 case_main + sys_employee
    const cases = await prisma.$queryRaw<
      { id: bigint; case_no: string }[]
    >`SELECT id, case_no FROM oa.case_main ORDER BY id DESC LIMIT 1`;
    const emps = await prisma.$queryRaw<
      { id: bigint }[]
    >`SELECT id FROM oa.sys_employee ORDER BY id LIMIT 1`;
    expect(cases.length).toBeGreaterThan(0);
    expect(emps.length).toBeGreaterThan(0);
    caseId = cases[0].id;
    uploader = emps[0].id;
  });

  afterAll(async () => {
    await app.close();
  });

  it('upload → presigned-url → download → delete 全链路', async () => {
    // upload（multipart）
    const up = await request(server)
      .post('/attachments/upload')
      .field('bizType', 'case')
      .field('bizId', String(caseId))
      .field('category', 'evidence')
      .field('uploadedBy', String(uploader))
      .field('entityType', 'case')
      .field('entityId', String(caseId))
      .field('fileUsage', '2')
      .attach('file', CONTENT, {
        filename: FILENAME,
        contentType: 'application/pdf',
      });
    expect(up.status).toBe(201);
    const upBody = up.body as unknown as { id: string };
    expect(upBody.id).toBeTruthy();
    const id = String(upBody.id);

    // 校验 sys_attachment 落库
    const att = await prisma.sys_attachment.findUnique({
      where: { id: BigInt(id) },
    });
    expect(att?.bucket).toBe('law-firm-files');
    expect(att?.storage_type).toBe('minio');
    expect(att?.object_key).toContain(`cases/${new Date().getUTCFullYear()}/`);

    // presigned-url
    const pre = await request(server).get(`/attachments/${id}/presigned-url`);
    expect(pre.status).toBe(200);
    const preBody = pre.body as unknown as { url: string };
    expect(preBody.url).toContain('law-firm-files');

    // download（二进制，字节一致）
    const dl = await request(server)
      .get(`/attachments/${id}/download`)
      .parse(binaryParse);
    expect(dl.status).toBe(200);
    expect((dl.body as Buffer).equals(CONTENT)).toBe(true);

    // delete（软删）
    const del = await request(server).delete(`/attachments/${id}`);
    expect(del.status).toBe(200);
    const delBody = del.body as unknown as { ok: boolean };
    expect(delBody.ok).toBe(true);

    // 软删后：对象消失 + deleted_at 非空
    const att2 = await prisma.sys_attachment.findUnique({
      where: { id: BigInt(id) },
    });
    expect(att2?.deleted_at).not.toBeNull();
    if (att?.object_key) {
      expect(await minio.fileExists(att.object_key)).toBe(false);
    }
  });

  it('upload 缺少 file → 400', async () => {
    const res = await request(server)
      .post('/attachments/upload')
      .field('bizType', 'case')
      .field('bizId', String(caseId))
      .field('category', 'evidence')
      .field('uploadedBy', String(uploader));
    expect(res.status).toBe(400);
  });

  it('upload 非法 category → 400', async () => {
    const res = await request(server)
      .post('/attachments/upload')
      .field('bizType', 'case')
      .field('bizId', String(caseId))
      .field('category', 'not_a_valid_category')
      .field('uploadedBy', String(uploader))
      .attach('file', CONTENT, FILENAME);
    expect(res.status).toBe(400);
  });
});
