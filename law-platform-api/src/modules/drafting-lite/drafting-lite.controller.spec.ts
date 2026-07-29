import { BadRequestException } from '@nestjs/common';
import { DraftingLiteController } from './drafting-lite.controller';
import { DraftingLiteService } from './drafting-lite.service';

describe('DraftingLiteController', () => {
  const drafting = {
    listCauses: jest.fn(),
    create: jest.fn(),
    confirmParties: jest.fn(),
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
});
