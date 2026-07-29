import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import LegalDraftingPanel from './LegalDraftingPanel';
import type { DraftingLiteJob } from './types';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function job(overrides: Partial<DraftingLiteJob> = {}): DraftingLiteJob {
  return {
    job_id: 'abcdef123456',
    status: 'queued',
    progress: 0,
    current_agent: 'coordinator',
    cause_requested: 'auto',
    cause_code: null,
    cause_label: null,
    confidence: null,
    template_name: null,
    cause_evidence: [],
    warnings: [],
    party_extraction: null,
    party_issues: [],
    party_confirmation_required: false,
    party_input_version: 0,
    error_message: null,
    download_url: null,
    created_at: '2026-07-23T00:00:00Z',
    updated_at: '2026-07-23T00:00:00Z',
    ...overrides,
  };
}

describe('LegalDraftingPanel', () => {
  const fetchMock = vi.fn<typeof fetch>();
  let responses: Response[] = [];
  const causeResponse = jsonResponse({
    items: [
      { code: 'private_lending', label: '民间借贷纠纷', template_name: '民间借贷.docx' },
      { code: 'labor_dispute', label: '劳动争议', template_name: '劳动争议.docx' },
    ],
  });

  function queueResponses(...items: Response[]) {
    responses.push(...items);
  }

  function callFor(path: string) {
    return fetchMock.mock.calls.find(([input]) => String(input) === path);
  }

  beforeEach(() => {
    fetchMock.mockReset();
    responses = [];
    sessionStorage.clear();
    fetchMock.mockImplementation(async (input) => {
      if (String(input) === '/api/drafting-lite/causes') return causeResponse.clone();
      const response = responses.shift();
      if (!response) throw new Error(`Unexpected fetch: ${String(input)}`);
      return response;
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    sessionStorage.clear();
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('uploads local materials without case, lawyer or material ids', async () => {
    queueResponses(jsonResponse(job()));
    render(<LegalDraftingPanel />);

    expect(screen.queryByLabelText('案件 ID')).not.toBeInTheDocument();
    expect(screen.queryByText(/律师审核/)).not.toBeInTheDocument();
    const file = new File(['借款合同内容'], '借款合同.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('选择当事人材料'), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole('button', { name: '分析材料并生成起诉状' }));

    expect(await screen.findByText('正在根据材料选择模板')).toBeVisible();
    const [path, init] = callFor('/api/drafting-lite/jobs')!;
    expect(path).toBe('/api/drafting-lite/jobs');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    const form = init?.body as FormData;
    expect(form.get('cause')).toBe('auto');
    expect((form.get('files') as File).name).toBe('借款合同.pdf');
    expect(form.get('knowledge_document_ids')).toBe('[]');
  });

  it('creates a job from a selected knowledge-base client material without an upload', async () => {
    queueResponses(
      jsonResponse({
        items: [{
          document_id: '290',
          title: '陶士娇卷宗',
          file_name: '陶士娇卷宗.pdf',
          category_path: ['当事人案件材料', '未结案'],
          embedding_status: 'success',
          last_uploaded_at: '2026-07-23T00:00:00Z',
          source_count: 1,
          image_total: 18,
        }],
        total: 1,
        page: 1,
        page_size: 10,
      }),
      jsonResponse(job({
        input_mode: 'knowledge',
        selected_materials: [{
          source_kind: 'knowledge',
          document_id: '290',
          title: '陶士娇卷宗',
          status: 'success',
        }],
      })),
    );
    render(<LegalDraftingPanel />);

    fireEvent.click(screen.getByRole('button', { name: '从知识库选择' }));
    expect(await screen.findByText('陶士娇卷宗')).toBeVisible();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '完成选择' }));
    fireEvent.click(screen.getByRole('button', { name: '分析材料并生成起诉状' }));

    expect(await screen.findByText('正在根据材料选择模板')).toBeVisible();
    const [path, init] = callFor('/api/drafting-lite/jobs')!;
    expect(path).toBe('/api/drafting-lite/jobs');
    const form = init?.body as FormData;
    expect(form.getAll('files')).toHaveLength(0);
    expect(form.get('knowledge_document_ids')).toBe('["290"]');
  });

  it('combines a knowledge-base material with a local supplementary upload', async () => {
    queueResponses(
      jsonResponse({
        items: [{
          document_id: '290',
          title: '陶士娇卷宗',
          file_name: '陶士娇卷宗.pdf',
          category_path: ['当事人案件材料', '未结案'],
          embedding_status: 'success',
          last_uploaded_at: '2026-07-23T00:00:00Z',
          source_count: 1,
          image_total: 18,
        }],
        total: 1,
        page: 1,
        page_size: 10,
      }),
      jsonResponse(job({ input_mode: 'mixed' })),
    );
    render(<LegalDraftingPanel />);

    fireEvent.click(screen.getByRole('button', { name: '从知识库选择' }));
    expect(await screen.findByText('陶士娇卷宗')).toBeVisible();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '完成选择' }));
    const supplement = new File(['补充聊天记录'], '补充材料.docx');
    fireEvent.change(screen.getByLabelText('选择当事人材料'), {
      target: { files: [supplement] },
    });
    fireEvent.click(screen.getByRole('button', { name: '分析材料并生成起诉状' }));

    await screen.findByText('正在根据材料选择模板');
    const form = callFor('/api/drafting-lite/jobs')![1]?.body as FormData;
    expect((form.get('files') as File).name).toBe('补充材料.docx');
    expect(form.get('knowledge_document_ids')).toBe('["290"]');
  });

  it('lets the user select a supported cause only when materials are insufficient', async () => {
    queueResponses(
      jsonResponse(job({
        status: 'waiting_cause_selection',
        progress: 35,
        confidence: 0.2,
        warnings: ['材料不足以可靠判断案由，请手工选择后继续'],
      })),
      jsonResponse(job({
        status: 'queued',
        cause_requested: 'labor_dispute',
      })),
    );
    render(<LegalDraftingPanel />);
    fireEvent.change(screen.getByLabelText('选择当事人材料'), {
      target: { files: [new File(['身份证'], '身份证.docx')] },
    });
    fireEvent.click(screen.getByRole('button', { name: '分析材料并生成起诉状' }));

    expect(await screen.findByText('材料不足以可靠判断案由')).toBeVisible();
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'labor_dispute' } });
    fireEvent.click(screen.getByRole('button', { name: '按所选案由继续生成' }));

    await waitFor(() => expect(callFor('/api/drafting-lite/jobs/abcdef123456/cause')).toBeDefined());
    const causeCall = callFor('/api/drafting-lite/jobs/abcdef123456/cause')!;
    expect(JSON.parse(String(causeCall[1]?.body))).toEqual({ cause: 'labor_dispute' });
  });

  it('automatically downloads the completed DOCX and keeps a retry button', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:draft'),
      revokeObjectURL: vi.fn(),
    });
    queueResponses(
      jsonResponse(job({
        status: 'completed',
        progress: 100,
        cause_code: 'private_lending',
        cause_label: '民间借贷纠纷',
        confidence: 0.96,
        template_name: '要素式民间借贷纠纷起诉状.docx',
        download_url: '/api/drafting-lite/jobs/abcdef123456/download',
      })),
      new Response(new Blob(['docx']), {
        status: 200,
        headers: {
          'content-type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'content-disposition': "attachment; filename*=UTF-8''draft.docx",
        },
      }),
    );
    render(<LegalDraftingPanel />);
    fireEvent.change(screen.getByLabelText('选择当事人材料'), {
      target: { files: [new File(['借条'], '借条.pdf')] },
    });
    fireEvent.click(screen.getByRole('button', { name: '分析材料并生成起诉状' }));

    expect(await screen.findByText('要素式起诉状已生成')).toBeVisible();
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: '重新下载 DOCX' })).toBeVisible();
  });

  it('edits and confirms versioned public party extraction results', async () => {
    const waiting = job({
      status: 'waiting_party_confirmation',
      progress: 42,
      cause_code: 'private_lending',
      cause_label: '民间借贷纠纷',
      party_confirmation_required: true,
      party_input_version: 3,
      party_issues: [{
        code: 'party_field_conflict',
        message: '原告姓名存在冲突',
        party_id: 'p1',
        field: 'name',
      }],
      party_extraction: {
        schema_version: 'party-extraction.v1',
        warnings: [],
        parties: [{
          party_id: 'p1',
          role: 'plaintiff',
          entity_type: 'natural_person',
          name: '张三',
          id_number: '110101199001010015',
          address: '北京市测试路1号',
          field_provenance: {
            name: [{ source_type: 'material', file_name: '身份证.pdf', page_no: 1 }],
          },
          field_conflicts: {},
        }, {
          party_id: 'p2',
          role: 'defendant',
          entity_type: 'organization',
          organization_name: '示例公司',
          unified_social_credit_code: '91110000100000000A',
          organization_address: '北京市测试路2号',
          field_provenance: {},
          field_conflicts: {},
        }],
      },
    });
    queueResponses(
      jsonResponse(waiting),
      jsonResponse(job({
        status: 'queued',
        cause_code: 'private_lending',
        party_input_version: 4,
        party_extraction: waiting.party_extraction,
      })),
    );
    render(<LegalDraftingPanel />);
    fireEvent.change(screen.getByLabelText('选择当事人材料'), {
      target: { files: [new File(['身份证'], '身份证.pdf')] },
    });
    fireEvent.click(screen.getByRole('button', { name: '分析材料并生成起诉状' }));

    expect(await screen.findByText('确认当事人信息')).toBeVisible();
    await screen.findByDisplayValue('张三');
    expect(screen.getByText('来源：身份证.pdf第1页')).toBeVisible();
    const names = screen.getAllByDisplayValue('张三');
    fireEvent.change(names[0], { target: { value: '张三（确认）' } });
    fireEvent.click(screen.getByRole('button', { name: '确认当事人并继续生成' }));

    await waitFor(() => expect(callFor('/api/drafting-lite/jobs/abcdef123456/parties')).toBeDefined());
    const confirmCall = callFor('/api/drafting-lite/jobs/abcdef123456/parties')!;
    const body = JSON.parse(String(confirmCall[1]?.body));
    expect(body.version).toBe(3);
    expect(body.confirmed).toBe(true);
    expect(body.parties[0].name).toBe('张三（确认）');
  });

  it('rejects unsupported local file types before upload', () => {
    render(<LegalDraftingPanel />);
    fireEvent.change(screen.getByLabelText('选择当事人材料'), {
      target: { files: [new File(['x'], '材料.txt')] },
    });
    expect(screen.getByRole('alert')).toHaveTextContent('仅支持 PDF、DOC 和 DOCX');
    expect(screen.getByRole('button', { name: '分析材料并生成起诉状' })).toBeDisabled();
  });
});
