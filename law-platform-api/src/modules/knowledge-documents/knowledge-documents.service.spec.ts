import { BadRequestException } from '@nestjs/common';
import { MinioService } from '../../core/minio/minio.service';
import { PrismaService } from '../../core/prisma/prisma.service';
import { RagService } from '../rag/rag.service';
import {
  KnowledgeDocumentsService,
  normalizeFilename,
  validateKnowledgeFile,
} from './knowledge-documents.service';

function uploadFile(
  name: string,
  contents: string,
  mimetype: string,
): Express.Multer.File {
  const buffer = Buffer.from(contents, 'utf8');
  return {
    fieldname: 'file',
    originalname: name,
    encoding: '7bit',
    mimetype,
    size: buffer.length,
    buffer,
    destination: '',
    filename: name,
    path: '',
    stream: undefined as never,
  };
}

describe('KnowledgeDocumentsService', () => {
  const existingAttachment = {
    id: BigInt(8),
    original_file_name: '劳动合同法.md',
    file_name: '劳动合同法.md',
    file_size: BigInt(128),
    kb_document: [
      {
        id: BigInt(12),
        doc_title: '中华人民共和国劳动合同法',
        legal_category: '法规',
        embedding_status: 'success',
        created_at: new Date('2026-07-16T00:00:00Z'),
      },
    ],
  };

  it('accepts UTF-8 text and rejects spoofed file signatures or MIME types', () => {
    expect(() =>
      validateKnowledgeFile(
        Buffer.from('# 劳动合同法'),
        '劳动合同法.md',
        'text/markdown',
      ),
    ).not.toThrow();
    expect(() =>
      validateKnowledgeFile(
        Buffer.from('not a pdf'),
        'fake.pdf',
        'application/pdf',
      ),
    ).toThrow(BadRequestException);
    expect(() =>
      validateKnowledgeFile(Buffer.from('plain text'), 'note.txt', 'image/png'),
    ).toThrow('文件 MIME 类型与扩展名不匹配');
  });

  it('normalizes browser mojibake filenames without changing safe ASCII names', () => {
    expect(normalizeFilename('law.md')).toBe('law.md');
    expect(normalizeFilename('å³å¨æ³.md')).toBe('劳动法.md');
  });

  it('reuses an exact-content document without uploading or vectorizing again', async () => {
    const prisma = {
      sys_attachment: {
        findFirst: jest.fn().mockResolvedValue(existingAttachment),
      },
      $queryRaw: jest
        .fn()
        .mockResolvedValue([{ upload_timings: null, ingest_timings: null }]),
    };
    const storage = { uploadFile: jest.fn() };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
    );

    await expect(
      service.create(
        uploadFile('劳动合同法.md', '# 劳动合同法', 'text/markdown'),
        {
          title: '重复标题不会覆盖原文档',
          category: '法规',
        },
      ),
    ).resolves.toMatchObject({
      deduplicated: true,
      document: { doc_id: '12', title: '中华人民共和国劳动合同法' },
    });
    expect(storage.uploadFile).not.toHaveBeenCalled();
  });

  it('uploads to MinIO and creates attachment plus public kb_document in one transaction', async () => {
    const attachment = {
      id: BigInt(21),
      original_file_name: '新法规.md',
      file_name: '新法规.md',
      file_size: BigInt(15),
    };
    const document = {
      id: BigInt(31),
      doc_title: '新法规',
      legal_category: '法规',
      embedding_status: 'pending',
      created_at: new Date('2026-07-16T00:00:00Z'),
    };
    const tx = {
      sys_attachment: { create: jest.fn().mockResolvedValue(attachment) },
      kb_document: { create: jest.fn().mockResolvedValue(document) },
      $executeRaw: jest.fn().mockResolvedValue(1),
    };
    const prisma = {
      sys_attachment: { findFirst: jest.fn().mockResolvedValue(null) },
      $transaction: jest.fn((callback: (client: typeof tx) => unknown) =>
        callback(tx),
      ),
      $executeRaw: jest.fn().mockResolvedValue(1),
      $queryRaw: jest.fn().mockResolvedValue([]),
    };
    const storage = {
      uploadFile: jest.fn().mockResolvedValue({
        bucket: 'law-firm-files',
        objectKey: 'key',
        etag: 'etag',
        size: 15,
      }),
      deleteFile: jest.fn(),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
    );

    await expect(
      service.create(uploadFile('新法规.md', '# 新法规内容', 'text/markdown'), {
        title: '新法规',
        category: '法规',
      }),
    ).resolves.toMatchObject({
      deduplicated: false,
      document: { doc_id: '31' },
    });
    /* Jest asymmetric matchers are intentionally typed as any. */

    /* Jest asymmetric matchers are intentionally typed as any. */
    /* eslint-disable @typescript-eslint/no-unsafe-assignment */
    expect(tx.sys_attachment.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          biz_type: 'knowledge_base',
          file_hash: expect.stringMatching(/^[a-f0-9]{64}$/),
          uploaded_by: null,
        }),
      }),
    );
    expect(tx.kb_document.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          permission_level: 'public',
          embedding_status: 'pending',
          created_by: null,
        }),
      }),
    );
    /* eslint-enable @typescript-eslint/no-unsafe-assignment */

    expect(storage.deleteFile).not.toHaveBeenCalled();
    expect(prisma.$executeRaw).toHaveBeenCalledTimes(2);
  });

  it('removes the uploaded object when the database transaction fails', async () => {
    const prisma = {
      sys_attachment: { findFirst: jest.fn().mockResolvedValue(null) },
      $queryRaw: jest.fn().mockResolvedValue([]),
      $transaction: jest
        .fn()
        .mockRejectedValue(new Error('database unavailable')),
    };
    const storage = {
      uploadFile: jest.fn().mockResolvedValue({
        bucket: 'law-firm-files',
        objectKey: 'key',
        etag: 'etag',
        size: 12,
      }),
      deleteFile: jest.fn().mockResolvedValue(undefined),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
    );

    await expect(
      service.create(uploadFile('失败.md', '# 内容', 'text/markdown'), {
        title: '失败文档',
        category: '工作资料',
      }),
    ).rejects.toThrow('database unavailable');
    expect(storage.deleteFile).toHaveBeenCalledWith(
      expect.stringContaining('knowledge-base/'),
      'law-firm-files',
    );
  });

  it('ingests a hidden staging document and promotes it while preserving the target id', async () => {
    const current = {
      id: BigInt(30),
      doc_title: '原标题',
      doc_type: '案例',
      legal_category: '案例',
      embedding_status: 'success',
      version_no: 'v1',
      permission_level: 'public',
      source_department_id: null,
      author_employee_id: null,
      created_by: null,
      sys_attachment: { id: BigInt(91), file_hash: 'old-hash' },
    };
    const attachment = {
      id: BigInt(101),
      original_file_name: '新版.md',
      file_name: '新版.md',
      file_size: BigInt(20),
    };
    const stagingDocument = { id: BigInt(41) };
    const tx = {
      sys_attachment: { create: jest.fn().mockResolvedValue(attachment) },
      kb_document: { create: jest.fn().mockResolvedValue(stagingDocument) },
    };
    const summaryRow = {
      doc_id: BigInt(30),
      attachment_id: BigInt(101),
      title: '新标题',
      category: '法规',
      embedding_status: 'success',
      file_name: '新版.md',
      file_size: BigInt(20),
      image_total: 0,
      created_at: new Date('2026-07-16T00:00:00Z'),
      upload_timings: null,
      ingest_timings: null,
    };
    const prisma = {
      kb_document: { findFirst: jest.fn().mockResolvedValue(current) },
      sys_attachment: { findFirst: jest.fn().mockResolvedValue(null) },
      $transaction: jest.fn((callback: (client: typeof tx) => unknown) =>
        callback(tx),
      ),
      $executeRaw: jest.fn().mockResolvedValue(1),
      $queryRaw: jest.fn().mockResolvedValue([summaryRow]),
    };
    const storage = {
      uploadFile: jest.fn().mockResolvedValue({
        bucket: 'law-firm-files',
        objectKey: 'staging-key',
        etag: 'etag',
        size: 20,
      }),
      deleteFile: jest.fn(),
    };
    const rag = {
      ingestDocument: jest.fn().mockResolvedValue({ status: 'success' }),
      promoteDocument: jest.fn().mockResolvedValue({ chunk_count: 4 }),
      cleanupStagingDocument: jest.fn(),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
    );

    await expect(
      service.replace(
        BigInt(30),
        uploadFile('新版.md', '# 新版本内容', 'text/markdown'),
        { title: '新标题', category: '法规' },
      ),
    ).resolves.toMatchObject({
      replaced: true,
      chunk_count: 4,
      document: { doc_id: '30', title: '新标题' },
    });
    /* eslint-disable @typescript-eslint/no-unsafe-assignment */
    expect(tx.sys_attachment.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ biz_type: 'knowledge_base_staging' }),
      }),
    );
    expect(tx.kb_document.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ status: 'staging' }),
      }),
    );
    /* eslint-enable @typescript-eslint/no-unsafe-assignment */
    expect(rag.ingestDocument).toHaveBeenCalledWith('41', true);
    expect(rag.promoteDocument).toHaveBeenCalledWith('41', '30');
    expect(rag.cleanupStagingDocument).not.toHaveBeenCalled();
  });

  it('appends a source through staging and keeps the original document id', async () => {
    const current = {
      id: BigInt(30),
      doc_title: '多源知识库',
      doc_type: '工作资料',
      legal_category: '工作资料',
      embedding_status: 'success',
      version_no: 'v1',
      permission_level: 'public',
      source_department_id: null,
      author_employee_id: null,
      created_by: null,
      sys_attachment: { id: BigInt(91), file_hash: 'old-hash' },
    };
    const attachment = {
      id: BigInt(102),
      original_file_name: '后续.md',
      file_name: '后续.md',
      file_size: BigInt(20),
    };
    const tx = {
      sys_attachment: { create: jest.fn().mockResolvedValue(attachment) },
      kb_document: { create: jest.fn().mockResolvedValue({ id: BigInt(42) }) },
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([{ next_order: 1 }])
        .mockResolvedValueOnce([{ id: BigInt(82) }]),
    };
    const sourceRow = {
      source_id: BigInt(82),
      document_id: BigInt(30),
      attachment_id: BigInt(102),
      source_title: '后续材料',
      sort_order: 1,
      is_primary: false,
      ingest_status: 'success',
      chunk_count: 2,
      image_total: 0,
      image_kept: 0,
      image_filtered: 0,
      file_name: '后续.md',
      file_size: BigInt(20),
      upload_timings: null,
      ingest_timings: null,
    };
    const summaryRow = {
      doc_id: BigInt(30),
      attachment_id: BigInt(91),
      title: '多源知识库',
      category: '工作资料',
      embedding_status: 'success',
      file_name: '主文件.md',
      file_size: BigInt(20),
      source_count: BigInt(2),
      image_total: 0,
      created_at: new Date('2026-07-16T00:00:00Z'),
      upload_timings: null,
      ingest_timings: null,
    };
    const prisma = {
      kb_document: { findFirst: jest.fn().mockResolvedValue(current) },
      $transaction: jest.fn((callback: (client: typeof tx) => unknown) =>
        callback(tx),
      ),
      $executeRaw: jest.fn().mockResolvedValue(1),
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([sourceRow])
        .mockResolvedValueOnce([summaryRow]),
    };
    const storage = {
      uploadFile: jest.fn().mockResolvedValue({
        bucket: 'law-firm-files',
        objectKey: 'staging-source-key',
        etag: 'etag',
        size: 20,
      }),
      deleteFile: jest.fn(),
    };
    const rag = {
      ingestDocument: jest.fn().mockResolvedValue({ status: 'success' }),
      promoteSource: jest.fn().mockResolvedValue({ chunk_count: 5 }),
      cleanupStagingDocument: jest.fn(),
    };
    const service = new KnowledgeDocumentsService(
      prisma as unknown as PrismaService,
      storage as unknown as MinioService,
      rag as unknown as RagService,
    );

    await expect(
      service.appendSource(
        BigInt(30),
        uploadFile('后续.md', '# 后续来源内容', 'text/markdown'),
        { source_title: '后续材料' },
      ),
    ).resolves.toMatchObject({
      document: { doc_id: '30', source_count: 2 },
      source: { source_id: '82', source_title: '后续材料' },
      chunk_count: 5,
    });
    expect(rag.promoteSource).toHaveBeenCalledWith(
      expect.objectContaining({
        stagingDocId: '42',
        targetDocId: '30',
        sourceId: '82',
        mode: 'append',
      }),
    );
    expect(rag.cleanupStagingDocument).not.toHaveBeenCalled();
    expect(storage.deleteFile).not.toHaveBeenCalled();
  });
});
