import { BadRequestException } from '@nestjs/common';
import { DraftingLiteController } from './drafting-lite.controller';
import { DraftingLiteService } from './drafting-lite.service';

describe('DraftingLiteController', () => {
  const drafting = {
    listCauses: jest.fn(),
    create: jest.fn(),
    cancel: jest.fn(),
    confirmParties: jest.fn(),
    downloadArtifact: jest.fn(),
  };
  const controller = new DraftingLiteController(
    drafting as unknown as DraftingLiteService,
  );

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('proxies the Python-owned dynamic cause catalog', async () => {
    drafting.listCauses.mockResolvedValue({
      items: [
        {
          code: 'future_cause',
          label: '未来案由',
          template_name: '未来案由.docx',
        },
      ],
    });

    await expect(controller.causes()).resolves.toEqual({
      items: [
        {
          code: 'future_cause',
          label: '未来案由',
          template_name: '未来案由.docx',
        },
      ],
    });
    expect(drafting.listCauses).toHaveBeenCalledTimes(1);
  });

  it('does not maintain a hard-coded cause allowlist', async () => {
    drafting.create.mockResolvedValue({ job_id: 'job-1' });
    await controller.create([], 'future_cause', '["123"]');
    expect(drafting.create).toHaveBeenCalledWith([], 'future_cause', ['123']);
  });

  it('forwards intelligent complaint cancellation', async () => {
    drafting.cancel.mockResolvedValue({
      job_id: 'job-1',
      status: 'cancelled',
    });

    await expect(controller.cancel('job-1')).resolves.toEqual({
      job_id: 'job-1',
      status: 'cancelled',
    });
    expect(drafting.cancel).toHaveBeenCalledWith('job-1');
  });

  it('validates and forwards versioned party confirmation', async () => {
    drafting.confirmParties.mockResolvedValue({
      job_id: 'job-1',
      status: 'queued',
    });
    const body = {
      version: 4,
      parties: [
        {
          party_id: 'party-1',
          role: 'plaintiff' as const,
          entity_type: 'natural_person' as const,
          name: '张三',
          field_provenance: {},
          field_conflicts: {},
        },
      ],
      confirmed: true,
    };

    await controller.confirmParties('job-1', body);
    expect(drafting.confirmParties).toHaveBeenCalledWith('job-1', body);
  });

  it('rejects stale-shaped or unconfirmed party requests locally', () => {
    expect(() =>
      controller.confirmParties('job-1', {
        version: -1,
        parties: [],
        confirmed: true,
      }),
    ).toThrow(BadRequestException);
    expect(() =>
      controller.confirmParties('job-1', {
        version: 1,
        parties: [],
        confirmed: false,
      }),
    ).toThrow(BadRequestException);
  });

  it('validates and proxies evidence directory downloads', async () => {
    drafting.downloadArtifact.mockResolvedValue({
      body: Buffer.from('docx'),
      contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      disposition: "attachment; filename*=UTF-8''evidence.docx",
    });

    await controller.downloadArtifact('job-1', 'evidence_directory');
    expect(drafting.downloadArtifact).toHaveBeenCalledWith(
      'job-1',
      'evidence_directory',
    );
    drafting.downloadArtifact.mockResolvedValue({
      body: Buffer.from('zip'),
      contentType: 'application/zip',
      disposition: "attachment; filename*=UTF-8''evidence.zip",
    });
    await controller.downloadArtifact('job-1', 'evidence_package');
    expect(drafting.downloadArtifact).toHaveBeenCalledWith(
      'job-1',
      'evidence_package',
    );
    await expect(
      controller.downloadArtifact('job-1', 'unknown'),
    ).rejects.toThrow(BadRequestException);
  });
});
