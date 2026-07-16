/**
 * 附件服务端到端验证 —— 对照 Python `verify_attachment_service.py`。
 * 用 Jest e2e（ts-jest 完整支持 decorator metadata，NestJS DI 正常）。
 * 连真实 PG + 真实 MinIO，9 步断言；固定文件名保证幂等可重跑。
 *
 * 运行：pnpm verify
 * 前置：需先有种子数据（case_main + sys_employee），如无请先跑
 *   law-rag-service 的 tmp_case_management_flow_test.py。
 */
import { Test, TestingModule } from '@nestjs/testing';
import { AppModule } from '../src/app.module';
import { AttachmentService } from '../src/modules/attachments/attachment.service';
import { PrismaService } from '../src/core/prisma/prisma.service';
import { MinioService } from '../src/core/minio/minio.service';

const CONTENT = Buffer.from(
  'minio 附件业务绑定端到端验证 测试证据清单',
  'utf8',
);
const FILENAME = '_attachment_service_probe.pdf';
const CATEGORY = 'evidence';
const BIZ_TYPE = 'case';
const ENTITY_TYPE = 'case';
const FILE_USAGE = 2;

describe('AttachmentService (e2e)', () => {
  let moduleFixture: TestingModule;
  let svc: AttachmentService;
  let prisma: PrismaService;
  let minio: MinioService;

  beforeAll(async () => {
    moduleFixture = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
    await moduleFixture.init(); // 触发 onModuleInit（PrismaService.$connect / MinioService 初始化 client）
    svc = moduleFixture.get(AttachmentService);
    prisma = moduleFixture.get(PrismaService);
    minio = moduleFixture.get(MinioService);
  });

  afterAll(async () => {
    await moduleFixture.close();
  });

  it('upload→写库→MinIO→download→presigned→relation→软删 全链路', async () => {
    // [0] cleanup（幂等）：清掉上次 probe 残留
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

    // [1] 取种子 case_main + sys_employee
    const cases = await prisma.$queryRaw<
      { id: bigint; case_no: string }[]
    >`SELECT id, case_no FROM oa.case_main ORDER BY id DESC LIMIT 1`;
    const emps = await prisma.$queryRaw<
      { id: bigint }[]
    >`SELECT id FROM oa.sys_employee ORDER BY id LIMIT 1`;
    expect(cases.length).toBeGreaterThan(0); // 无种子请先跑 tmp_case_management_flow_test.py
    expect(emps.length).toBeGreaterThan(0);
    const caseId = cases[0].id;
    const caseNo = cases[0].case_no;
    const uploader = emps[0].id;

    // [2] upload
    const aid = await svc.upload({
      fileData: CONTENT,
      filename: FILENAME,
      bizType: BIZ_TYPE,
      bizId: caseId,
      category: CATEGORY,
      uploadedBy: uploader,
      entityType: ENTITY_TYPE,
      entityId: caseId,
      fileUsage: FILE_USAGE,
    });
    expect(aid > 0n).toBe(true);

    // [3] 校验 sys_attachment 字段
    const att = await prisma.sys_attachment.findUnique({ where: { id: aid } });
    expect(att).not.toBeNull();
    const a = att!;
    expect(a.bucket).toBe('law-firm-files');
    expect(a.storage_type).toBe('minio');
    expect(a.file_size).toBe(BigInt(CONTENT.length));
    expect(a.object_key).not.toBeNull();
    const year = new Date().getUTCFullYear();
    expect(a.object_key!.startsWith(`cases/${year}/`)).toBe(true);
    expect(a.object_key!.includes(caseNo)).toBe(true);
    expect(a.etag).toBeTruthy();
    expect(a.original_file_name).toBe(FILENAME);

    // [4] MinIO 对象存在
    expect(await minio.fileExists(a.object_key!)).toBe(true);

    // [5] download 字节一致
    const data = await svc.download(aid);
    expect(data.equals(CONTENT)).toBe(true);

    // [6] presigned url 含 bucket
    const url = await svc.getPresignedUrl(aid);
    expect(url).toContain('law-firm-files');

    // [7] 校验 sys_attachment_relation
    const rels = await prisma.$queryRaw<
      { entity_type: string; entity_id: bigint; file_usage: number | null }[]
    >`SELECT entity_type, entity_id, file_usage FROM oa.sys_attachment_relation WHERE attachment_id = ${aid}`;
    expect(rels.length).toBe(1);
    expect(rels[0].entity_type).toBe(ENTITY_TYPE);
    expect(rels[0].entity_id).toBe(caseId);
    expect(rels[0].file_usage).toBe(FILE_USAGE);

    // [8] 软删 → MinIO 对象消失 + deleted_at 非空
    await svc.delete(aid, true);
    expect(await minio.fileExists(a.object_key!)).toBe(false);
    const att2 = await prisma.sys_attachment.findUnique({
      where: { id: aid },
    });
    expect(att2!.deleted_at).not.toBeNull();
  });
});
