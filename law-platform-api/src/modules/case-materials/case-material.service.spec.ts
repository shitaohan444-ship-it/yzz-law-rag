import { NotFoundException } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import { PrismaService } from '../../core/prisma/prisma.service';
import { AttachmentService } from '../attachments/attachment.service';
import { CaseMaterialService } from './case-material.service';

describe('CaseMaterialService', () => {
  let service: CaseMaterialService;
  let tx: {
    case_material: { create: jest.Mock; update: jest.Mock };
  };
  let prisma: {
    $transaction: jest.Mock;
    case_material: {
      create: jest.Mock;
      findUnique: jest.Mock;
      update: jest.Mock;
    };
  };
  let attachments: {
    upload: jest.Mock;
    delete: jest.Mock;
    getDownload: jest.Mock;
  };

  beforeEach(async () => {
    tx = { case_material: { create: jest.fn(), update: jest.fn() } };
    prisma = {
      $transaction: jest.fn(
        async (callback: (value: typeof tx) => Promise<unknown>) =>
          callback(tx),
      ),
      case_material: {
        create: jest.fn(),
        findUnique: jest.fn(),
        update: jest.fn(),
      },
    };
    attachments = {
      upload: jest.fn(),
      delete: jest.fn(),
      getDownload: jest.fn(),
    };
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        CaseMaterialService,
        { provide: PrismaService, useValue: prisma },
        { provide: AttachmentService, useValue: attachments },
      ],
    }).compile();
    service = module.get(CaseMaterialService);
  });

  it('creates a case material associated with uploaded attachment', async () => {
    attachments.upload.mockResolvedValue(11n);
    tx.case_material.create.mockResolvedValue({ id: 21n });

    const result = await service.createWithFile({
      caseId: 1n,
      fileData: Buffer.from('abc'),
      filename: 'evidence.pdf',
      materialName: '证据',
      materialType: '证据材料',
      category: 'evidence',
      uploadedBy: 2n,
    });

    expect(result).toEqual({ id: 21n });
    expect(attachments.upload).toHaveBeenCalledWith(
      expect.objectContaining({ bizType: 'case', bizId: 1n }),
    );
    const createCall = tx.case_material.create.mock.calls[0] as unknown as [
      { data: { attachment_id: bigint; case_id: bigint } },
    ];
    expect(createCall[0].data.attachment_id).toBe(11n);
    expect(createCall[0].data.case_id).toBe(1n);
  });

  it('compensates attachment when case material database write rejects', async () => {
    const dbError = new Error('database unavailable');
    attachments.upload.mockResolvedValue(11n);
    prisma.$transaction.mockRejectedValue(dbError);
    attachments.delete.mockResolvedValue(undefined);

    await expect(
      service.createWithFile({
        caseId: 1n,
        fileData: Buffer.from('abc'),
        filename: 'evidence.pdf',
        materialName: '证据',
        materialType: '证据材料',
        category: 'evidence',
        uploadedBy: 2n,
      }),
    ).rejects.toBe(dbError);
    expect(attachments.delete).toHaveBeenCalledWith(11n, true);
  });

  it('replaces file association and soft deletes old attachment', async () => {
    prisma.case_material.findUnique.mockResolvedValue({
      id: 21n,
      case_id: 1n,
      attachment_id: 10n,
      deleted_at: null,
    });
    attachments.upload.mockResolvedValue(11n);
    tx.case_material.update.mockResolvedValue({ id: 21n });
    attachments.delete.mockResolvedValue(undefined);

    const result = await service.replaceFile(21n, {
      fileData: Buffer.from('new'),
      filename: 'new.pdf',
      category: 'evidence',
      uploadedBy: 2n,
    });

    expect(result).toEqual({ id: 21n, attachmentId: 11n });
    const updateCall = tx.case_material.update.mock.calls[0] as unknown as [
      { data: { attachment_id: bigint } },
    ];
    expect(updateCall[0].data.attachment_id).toBe(11n);
    expect(attachments.delete).toHaveBeenCalledWith(10n, true);
  });

  it('compensates new attachment when replace transaction rejects', async () => {
    const dbError = new Error('update failed');
    prisma.case_material.findUnique.mockResolvedValue({
      id: 21n,
      case_id: 1n,
      attachment_id: 10n,
      deleted_at: null,
    });
    attachments.upload.mockResolvedValue(11n);
    prisma.$transaction.mockRejectedValue(dbError);
    attachments.delete.mockResolvedValue(undefined);

    await expect(
      service.replaceFile(21n, {
        fileData: Buffer.from('new'),
        filename: 'new.pdf',
        category: 'evidence',
        uploadedBy: 2n,
      }),
    ).rejects.toBe(dbError);
    expect(attachments.delete).toHaveBeenCalledWith(11n, true);
  });

  it('soft deletes material and cascades attachment deletion', async () => {
    prisma.case_material.findUnique.mockResolvedValue({
      id: 21n,
      case_id: 1n,
      attachment_id: 10n,
      deleted_at: null,
    });
    tx.case_material.update.mockResolvedValue({ id: 21n });
    attachments.delete.mockResolvedValue(undefined);

    await service.remove(21n, 2n);

    const removeCall = tx.case_material.update.mock.calls[0] as unknown as [
      { data: { deleted_at: Date } },
    ];
    expect(removeCall[0].data.deleted_at).toBeInstanceOf(Date);
    expect(attachments.delete).toHaveBeenCalledWith(10n, true);
  });

  it('rejects missing material and material without electronic file', async () => {
    prisma.case_material.findUnique.mockResolvedValueOnce(null);
    await expect(service.findOne(999n)).rejects.toBeInstanceOf(
      NotFoundException,
    );

    prisma.case_material.findUnique.mockResolvedValueOnce({
      id: 21n,
      case_id: 1n,
      attachment_id: null,
      deleted_at: null,
    });
    await expect(service.download(21n)).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  it('propagates attachment upload promise rejection', async () => {
    const uploadError = new Error('MinIO unavailable');
    attachments.upload.mockRejectedValue(uploadError);

    await expect(
      service.createWithFile({
        caseId: 1n,
        fileData: Buffer.from('abc'),
        filename: 'evidence.pdf',
        materialName: '证据',
        materialType: '证据材料',
        category: 'evidence',
        uploadedBy: 2n,
      }),
    ).rejects.toBe(uploadError);
    expect(prisma.$transaction).not.toHaveBeenCalled();
  });
});
