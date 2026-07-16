import { Test, TestingModule } from '@nestjs/testing';
import { MinioService } from '../../core/minio/minio.service';
import { PrismaService } from '../../core/prisma/prisma.service';
import { AttachmentService } from './attachment.service';

describe('AttachmentService', () => {
  let service: AttachmentService;
  let prisma: {
    $transaction: jest.Mock;
    sys_attachment: { findUnique: jest.Mock };
  };
  let tx: {
    sys_attachment: {
      create: jest.Mock;
      findUnique: jest.Mock;
      update: jest.Mock;
      delete: jest.Mock;
    };
    sys_attachment_relation: { create: jest.Mock; deleteMany: jest.Mock };
  };
  let storage: {
    uploadFile: jest.Mock;
    downloadFile: jest.Mock;
    getPresignedUrl: jest.Mock;
    deleteFile: jest.Mock;
  };

  beforeEach(async () => {
    tx = {
      sys_attachment: {
        create: jest.fn(),
        findUnique: jest.fn(),
        update: jest.fn(),
        delete: jest.fn(),
      },
      sys_attachment_relation: {
        create: jest.fn(),
        deleteMany: jest.fn(),
      },
    };
    prisma = {
      $transaction: jest.fn(
        async (callback: (value: typeof tx) => Promise<unknown>) =>
          callback(tx),
      ),
      sys_attachment: { findUnique: jest.fn() },
    };
    storage = {
      uploadFile: jest.fn(),
      downloadFile: jest.fn(),
      getPresignedUrl: jest.fn(),
      deleteFile: jest.fn(),
    };
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AttachmentService,
        { provide: PrismaService, useValue: prisma },
        { provide: MinioService, useValue: storage },
      ],
    }).compile();
    service = module.get(AttachmentService);
  });

  it('uploads to MinIO, creates attachment and binds entity', async () => {
    storage.uploadFile.mockResolvedValue({
      bucket: 'law-firm-files',
      objectKey: 'cases/2026/07/C-1/evidence/a.pdf',
      etag: 'etag',
      size: 3,
    });
    tx.sys_attachment.create.mockResolvedValue({ id: 10n });
    tx.sys_attachment_relation.create.mockResolvedValue({ id: 20n });

    const id = await service.upload({
      fileData: Buffer.from('abc'),
      filename: 'a.pdf',
      bizType: 'case',
      bizId: 1n,
      category: 'evidence',
      uploadedBy: 2n,
      prefix: 'cases',
      entityNo: 'C-1',
      entityType: 'case',
      entityId: 1n,
    });

    expect(id).toBe(10n);
    expect(storage.uploadFile).toHaveBeenCalledTimes(1);
    expect(tx.sys_attachment.create).toHaveBeenCalledTimes(1);
    expect(tx.sys_attachment_relation.create).toHaveBeenCalledTimes(1);
  });

  it('compensates uploaded object when database transaction rejects', async () => {
    const dbError = new Error('database unavailable');
    storage.uploadFile.mockResolvedValue({
      bucket: 'law-firm-files',
      objectKey: 'cases/2026/07/C-1/evidence/a.pdf',
      etag: 'etag',
      size: 3,
    });
    prisma.$transaction.mockRejectedValue(dbError);
    storage.deleteFile.mockResolvedValue(undefined);

    await expect(
      service.upload({
        fileData: Buffer.from('abc'),
        filename: 'a.pdf',
        bizType: 'case',
        bizId: 1n,
        category: 'evidence',
        uploadedBy: 2n,
        prefix: 'cases',
        entityNo: 'C-1',
      }),
    ).rejects.toBe(dbError);
    expect(storage.deleteFile).toHaveBeenCalledTimes(1);
  });

  it('returns download metadata and presigned URL', async () => {
    prisma.sys_attachment.findUnique.mockResolvedValue({
      id: 10n,
      deleted_at: null,
      object_key: 'a.pdf',
      storage_path: 'a.pdf',
      mime_type: 'application/pdf',
      original_file_name: 'original.pdf',
      file_name: 'a.pdf',
    });
    storage.downloadFile.mockResolvedValue(Buffer.from('abc'));
    storage.getPresignedUrl.mockResolvedValue('https://minio/a');

    await expect(service.getDownload(10n)).resolves.toEqual({
      buffer: Buffer.from('abc'),
      mimeType: 'application/pdf',
      fileName: 'original.pdf',
    });
    await expect(service.getPresignedUrl(10n)).resolves.toBe('https://minio/a');
  });

  it('rejects missing or soft-deleted files', async () => {
    prisma.sys_attachment.findUnique.mockResolvedValue(null);

    await expect(service.download(999n)).rejects.toThrow('附件不存在或已删除');
  });

  it('soft deletes database row before deleting MinIO object', async () => {
    tx.sys_attachment.findUnique.mockResolvedValue({
      id: 10n,
      deleted_at: null,
      object_key: 'a.pdf',
      storage_path: 'a.pdf',
    });
    tx.sys_attachment.update.mockResolvedValue({ id: 10n });
    storage.deleteFile.mockResolvedValue(undefined);

    await service.delete(10n, true);

    expect(tx.sys_attachment.update).toHaveBeenCalledTimes(1);
    expect(storage.deleteFile).toHaveBeenCalledWith('a.pdf');
    expect(tx.sys_attachment.update.mock.invocationCallOrder[0]).toBeLessThan(
      storage.deleteFile.mock.invocationCallOrder[0],
    );
  });

  it('propagates MinIO upload promise rejection without database writes', async () => {
    const storageError = new Error('MinIO unavailable');
    storage.uploadFile.mockRejectedValue(storageError);

    await expect(
      service.upload({
        fileData: Buffer.from('abc'),
        filename: 'a.pdf',
        bizType: 'case',
        bizId: 1n,
        category: 'evidence',
        uploadedBy: 2n,
        prefix: 'cases',
        entityNo: 'C-1',
      }),
    ).rejects.toBe(storageError);
    expect(prisma.$transaction).not.toHaveBeenCalled();
  });
});
