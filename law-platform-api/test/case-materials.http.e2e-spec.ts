/**
 * 案件材料 HTTP API 端到端验证（案件附件集成）。
 * supertest 连真实 PG + MinIO，固定 material_name 前缀保证幂等。
 */
import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import request from 'supertest';
import { AppModule } from '../src/app.module';
import { PrismaService } from '../src/core/prisma/prisma.service';
import { MinioService } from '../src/core/minio/minio.service';
import type { Server } from 'node:http';

const CONTENT = Buffer.from('案件材料 http e2e 测试', 'utf8');
const FILENAME = '_cm_http_probe.pdf';
const PROBE_FILE = '_cm_http_probe_file'; // 带文件材料名
const PROBE_REG = '_cm_http_probe_reg'; // 纯登记材料名

interface CaseMaterialListItem {
  id: string;
  material_name: string;
  sys_attachment?: { file_name?: string; file_size?: string } | null;
}

const binaryParse = (
  res: { on: (e: string, cb: (c: Buffer) => void) => void },
  cb: (e: unknown, body: Buffer) => void,
) => {
  const chunks: Buffer[] = [];
  res.on('data', (c: Buffer) => chunks.push(c));
  res.on('end', () => cb(null, Buffer.concat(chunks)));
};

describe('CaseMaterials HTTP (e2e)', () => {
  let app: INestApplication;
  let server: Server;
  let prisma: PrismaService;
  let minio: MinioService;
  let caseId: bigint;
  let caseNo: string;
  let uploader: bigint;
  let matId: string; // 带文件材料
  let matAttId: string; // 其附件 id
  let regId: string; // 纯登记材料

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
    app = moduleFixture.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({ whitelist: true, transform: true }),
    );
    (BigInt.prototype as unknown as { toJSON: () => string }).toJSON =
      function () {
        return String(this);
      };
    await app.init();
    server = app.getHttpServer() as Server;

    prisma = app.get(PrismaService);
    minio = app.get(MinioService);

    // cleanup（幂等）：清掉所有 probe 材料 + 其附件 + MinIO 对象
    const stale = await prisma.$queryRaw<
      { id: bigint; attachment_id: bigint | null }[]
    >`SELECT id, attachment_id FROM oa.case_material WHERE material_name LIKE '_cm_http_probe%'`;
    for (const row of stale) {
      if (row.attachment_id) {
        const att = await prisma.sys_attachment.findUnique({
          where: { id: row.attachment_id },
        });
        if (att?.object_key)
          await minio.deleteFile(att.object_key).catch(() => {});
      }
      await prisma.$executeRaw`DELETE FROM oa.case_material WHERE id = ${row.id}`;
      if (row.attachment_id) {
        await prisma.$executeRaw`DELETE FROM oa.sys_attachment WHERE id = ${row.attachment_id}`.catch(
          () => {},
        );
      }
    }

    const cases = await prisma.$queryRaw<
      { id: bigint; case_no: string }[]
    >`SELECT id, case_no FROM oa.case_main ORDER BY id DESC LIMIT 1`;
    const emps = await prisma.$queryRaw<
      { id: bigint }[]
    >`SELECT id FROM oa.sys_employee ORDER BY id LIMIT 1`;
    expect(cases.length).toBeGreaterThan(0);
    expect(emps.length).toBeGreaterThan(0);
    caseId = cases[0].id;
    caseNo = cases[0].case_no;
    uploader = emps[0].id;
  });

  afterAll(async () => {
    await app.close();
  });

  it('1. 建材料带文件 → 列表含文件元信息', async () => {
    const up = await request(server)
      .post(`/cases/${caseId}/materials`)
      .field('materialName', PROBE_FILE)
      .field('materialType', '起诉状')
      .field('category', 'pleading')
      .field('uploadedBy', String(uploader))
      .attach('file', CONTENT, {
        filename: FILENAME,
        contentType: 'application/pdf',
      });
    expect(up.status).toBe(201);
    const upBody = up.body as unknown as { id: string };
    expect(upBody.id).toBeTruthy();
    matId = String(upBody.id);

    const cm = await prisma.case_material.findUnique({
      where: { id: BigInt(matId) },
    });
    expect(cm?.attachment_id).not.toBeNull();
    matAttId = String(cm!.attachment_id);

    const att = await prisma.sys_attachment.findUnique({
      where: { id: BigInt(matAttId) },
    });
    const year = new Date().getUTCFullYear();
    expect(att?.object_key).toContain(`cases/${year}/`);
    expect(att?.object_key).toContain(caseNo);
    expect(await minio.fileExists(att!.object_key!)).toBe(true);

    const list = await request(server).get(`/cases/${caseId}/materials`);
    expect(list.status).toBe(200);
    const listBody = list.body as unknown as { items: CaseMaterialListItem[] };
    const item = listBody.items.find(
      (candidate) => candidate.material_name === PROBE_FILE,
    );
    expect(item).toBeTruthy();
    expect(item.sys_attachment?.file_name).toBe(FILENAME);
    expect(item.sys_attachment?.file_size).toBe(String(CONTENT.length));
  });

  it('2. 纯登记材料（JSON）→ attachment_id=null + hasFile=false 过滤', async () => {
    const reg = await request(server)
      .post(`/cases/${caseId}/materials`)
      .set('Content-Type', 'application/json')
      .send({
        materialName: PROBE_REG,
        materialType: '证据清单',
        nasPath: '/nas/probe',
        uploadedBy: String(uploader),
      });
    expect(reg.status).toBe(201);
    const regBody = reg.body as unknown as { id: string };
    regId = String(regBody.id);

    const cm = await prisma.case_material.findUnique({
      where: { id: BigInt(regId) },
    });
    expect(cm?.attachment_id).toBeNull();
    expect(cm?.nas_path).toBe('/nas/probe');

    const list = await request(server).get(
      `/cases/${caseId}/materials?hasFile=false`,
    );
    expect(list.status).toBe(200);
    const listBody = list.body as unknown as { items: CaseMaterialListItem[] };
    const found = listBody.items.find((candidate) => candidate.id === regId);
    expect(found).toBeTruthy();
  });

  it('3. 无附件材料下载 → 404', async () => {
    const dl = await request(server).get(`/case-materials/${regId}/download`);
    expect(dl.status).toBe(404);
  });

  it('4. 后补文件 → attachment_id 由 null 变非空', async () => {
    const patch = await request(server)
      .post(`/case-materials/${regId}/file`)
      .field('category', 'evidence')
      .field('uploadedBy', String(uploader))
      .attach('file', CONTENT, FILENAME);
    expect(patch.status).toBe(201);

    const cm = await prisma.case_material.findUnique({
      where: { id: BigInt(regId) },
    });
    expect(cm?.attachment_id).not.toBeNull();
    const att = await prisma.sys_attachment.findUnique({
      where: { id: cm!.attachment_id! },
    });
    expect(await minio.fileExists(att!.object_key!)).toBe(true);
  });

  it('5. 便捷下载 → 字节一致', async () => {
    const dl = await request(server)
      .get(`/case-materials/${matId}/download`)
      .parse(binaryParse);
    expect(dl.status).toBe(200);
    expect((dl.body as Buffer).equals(CONTENT)).toBe(true);
  });

  it('6. 软删级联 → case_material + sys_attachment 都软删 + MinIO 对象消失', async () => {
    const del = await request(server).delete(
      `/case-materials/${matId}?operatorId=${uploader}`,
    );
    expect(del.status).toBe(200);
    const delBody = del.body as unknown as { ok: boolean };
    expect(delBody.ok).toBe(true);

    const cm = await prisma.case_material.findUnique({
      where: { id: BigInt(matId) },
    });
    expect(cm?.deleted_at).not.toBeNull();

    const att = await prisma.sys_attachment.findUnique({
      where: { id: BigInt(matAttId) },
    });
    expect(att?.deleted_at).not.toBeNull();
    expect(await minio.fileExists(att!.object_key!)).toBe(false);
  });

  it('边界：非法 category → 400', async () => {
    const bad = await request(server)
      .post(`/cases/${caseId}/materials`)
      .field('materialName', PROBE_FILE)
      .field('materialType', '起诉状')
      .field('category', 'not_a_valid_category')
      .field('uploadedBy', String(uploader))
      .attach('file', CONTENT, FILENAME);
    expect(bad.status).toBe(400);
  });

  it('边界：带文件缺 category → 400', async () => {
    const bad = await request(server)
      .post(`/cases/${caseId}/materials`)
      .field('materialName', PROBE_FILE)
      .field('materialType', '起诉状')
      .field('uploadedBy', String(uploader))
      .attach('file', CONTENT, FILENAME);
    expect(bad.status).toBe(400);
  });
});
