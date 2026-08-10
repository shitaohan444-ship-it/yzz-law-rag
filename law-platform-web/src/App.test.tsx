import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { createSessionId } from './session';
import { UploadActivityProvider } from './UploadActivityContext';

vi.mock('./session', () => ({ createSessionId: vi.fn() }));

const mockedSessionId = vi.mocked(createSessionId);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function kbEmptyResponse(): Response {
  return jsonResponse({ items: [], total: 0, page: 1, page_size: 10 });
}

function kbCategoriesResponse(): Response {
  return jsonResponse({
    items: [
      { category_id: '1', parent_id: null, category_name: '法律法规', code: 'laws', level: 1, path: ['法律法规'], assignable: true, is_system: false, status: 'active', children_count: 1 },
    ],
  });
}

describe('App', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    mockedSessionId.mockReset();
    mockedSessionId.mockReturnValueOnce('session-one').mockReturnValue('session-two');
    fetchMock.mockReset();
    // KnowledgePanel always mounts now; supply empty KB responses by default
    fetchMock.mockImplementation((url: RequestInfo | URL) => {
      const path = typeof url === 'string' ? new URL(url, 'http://localhost').pathname : new URL(String(url), 'http://localhost').pathname;
      if (path.includes('/api/rag/categories')) return Promise.resolve(kbCategoriesResponse());
      if (path.includes('/api/rag/documents')) return Promise.resolve(kbEmptyResponse());
      return Promise.resolve(jsonResponse({ error: 'unexpected-call' }, 500));
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('disables empty submission and renders ranked search results', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        query: '试用期工资',
        total: 1,
        hits: [
          {
            chunk_id: '1-0',
            doc_id: 1,
            doc_title: '中华人民共和国劳动合同法',
            source: '劳动合同法.md',
            chunk_idx: 0,
            text: '劳动者在试用期的工资不得低于约定工资的百分之八十。',
            score: 0.98,
            article_no: '第二十条',
            official_link: {
              provider: 'npc_flk',
              source_name: '国家法律法规数据库',
              label: '官网最新版',
              url: 'https://flk.npc.gov.cn/detail?id=0123456789abcdef0123456789abcdef',
            },
          },
        ],
      }),
    );
    render(<UploadActivityProvider><App /></UploadActivityProvider>);

    expect(screen.getByRole('tab', { name: /分类管理/ })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tab', { name: /回收站/ })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tab', { name: /智能起诉状/ })).toHaveAttribute('aria-selected', 'false');
    // 顶部六个一级模块，含多 Agent 要素式法律文书协作。
    expect(screen.getAllByRole('tab')).toHaveLength(6);

    const submit = screen.getByRole('button', { name: '开始检索' });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText('检索问题'), {
      target: { value: '试用期工资' },
    });
    fireEvent.click(submit);

    expect(await screen.findByText('中华人民共和国劳动合同法')).toBeVisible();
    expect(screen.getByText('第二十条')).toBeVisible();
    expect(screen.getByText('相关度 98.0%')).toBeVisible();
    expect(screen.getByRole('link', { name: /官网最新版/ })).toHaveAttribute(
      'href',
      'https://flk.npc.gov.cn/detail?id=0123456789abcdef0123456789abcdef',
    );
    expect(screen.getByRole('link', { name: /官网最新版/ })).toHaveAttribute(
      'target',
      '_blank',
    );
    expect(screen.getByRole('link', { name: /官网最新版/ })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    );
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/rag/search',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('renders markdown answers, references and reuses one page session', async () => {
    const response = {
      question: '产品缺陷造成损害怎么办',
      answer: '**生产者**应当承担侵权责任。[1]',
      refs: [
        {
          ref_id: 1,
          chunk_id: '2-0',
          doc_id: 2,
          doc_title: '中华人民共和国民法典',
          source: '民法典.md',
          chunk_idx: 0,
          text: '因产品存在缺陷造成他人损害的，生产者应当承担侵权责任。',
          score: 0.99,
          article_no: '第一千二百零二条',
          official_link: {
            provider: 'npc_flk',
            source_name: '国家法律法规数据库',
            label: '官网最新版',
            url: 'https://flk.npc.gov.cn/detail?id=fedcba9876543210fedcba9876543210',
          },
        },
      ],
      chat_log_id: 9,
      hits_count: 1,
    };
    fetchMock.mockResolvedValue(jsonResponse(response));
    render(<UploadActivityProvider><App /></UploadActivityProvider>);
    fireEvent.click(screen.getByRole('tab', { name: /知识问答/ }));

    const input = screen.getByLabelText('法律问题');
    fireEvent.change(input, { target: { value: '产品缺陷造成损害怎么办' } });
    fireEvent.click(screen.getByRole('button', { name: '提交问题' }));
    expect(await screen.findByText('生产者')).toBeVisible();
    expect(screen.getAllByText('第一千二百零二条')[0]).toBeVisible();
    expect(screen.getByRole('link', { name: /官网最新版/ })).toBeVisible();

    fireEvent.change(input, { target: { value: '再问一次' } });
    fireEvent.click(screen.getByRole('button', { name: '提交问题' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const bodies = fetchMock.mock.calls.map((call) =>
      JSON.parse(String(call[1]?.body)) as { session_id: string },
    );
    expect(bodies[0].session_id).toBe('session-one');
    expect(bodies[1].session_id).toBe('session-one');
  });

  it('does not render missing or unsafe official links', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        query: '测试',
        total: 2,
        hits: [
          {
            chunk_id: 'safe-without-link',
            doc_id: 1,
            doc_title: '无映射法规',
            source: '法律',
            chunk_idx: 0,
            text: '正文',
            score: 0.8,
          },
          {
            chunk_id: 'unsafe-link',
            doc_id: 2,
            doc_title: '非法链接法规',
            source: '法律',
            chunk_idx: 0,
            text: '正文',
            score: 0.7,
            official_link: {
              provider: 'npc_flk',
              source_name: '国家法律法规数据库',
              label: '官网最新版',
              url: 'javascript:alert(1)',
            },
          },
        ],
      }),
    );
    render(<UploadActivityProvider><App /></UploadActivityProvider>);
    fireEvent.change(screen.getByLabelText('检索问题'), {
      target: { value: '测试' },
    });
    fireEvent.click(screen.getByRole('button', { name: '开始检索' }));
    expect(await screen.findByText('无映射法规')).toBeVisible();
    expect(screen.queryByRole('link', { name: /官网最新版/ })).not.toBeInTheDocument();
  });

  it('creates a new session after the page is remounted', () => {
    const first = render(<UploadActivityProvider><App /></UploadActivityProvider>);
    expect(mockedSessionId).toHaveBeenCalledTimes(1);
    first.unmount();
    render(<UploadActivityProvider><App /></UploadActivityProvider>);
    expect(mockedSessionId).toHaveBeenCalledTimes(2);
  });

  it('shows an explicit insufficient-knowledge notice and safe errors', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          question: '量刑标准是什么',
          answer: '现有知识库中没有足够依据回答该问题。',
          refs: [],
          chat_log_id: null,
          hits_count: 0,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ code: 'RAG_TIMEOUT', message: '知识库处理超时，请稍后重试' }, 504),
      );
    render(<UploadActivityProvider><App /></UploadActivityProvider>);
    fireEvent.click(screen.getByRole('tab', { name: /知识问答/ }));
    const input = screen.getByLabelText('法律问题');
    fireEvent.change(input, { target: { value: '量刑标准是什么' } });
    fireEvent.click(screen.getByRole('button', { name: '提交问题' }));
    expect(await screen.findByText('知识库依据不足')).toBeVisible();

    fireEvent.change(input, { target: { value: '再次提问' } });
    fireEvent.click(screen.getByRole('button', { name: '提交问题' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('知识库处理超时');
  });
});
