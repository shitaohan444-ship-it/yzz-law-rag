import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { createSessionId } from './session';

vi.mock('./session', () => ({ createSessionId: vi.fn() }));

const mockedSessionId = vi.mocked(createSessionId);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('App', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    mockedSessionId.mockReset();
    mockedSessionId.mockReturnValueOnce('session-one').mockReturnValue('session-two');
    fetchMock.mockReset();
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
          },
        ],
      }),
    );
    render(<App />);

    const submit = screen.getByRole('button', { name: '开始检索' });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText('检索问题'), {
      target: { value: '试用期工资' },
    });
    fireEvent.click(submit);

    expect(await screen.findByText('中华人民共和国劳动合同法')).toBeVisible();
    expect(screen.getByText('第二十条')).toBeVisible();
    expect(screen.getByText('相关度 98.0%')).toBeVisible();
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
        },
      ],
      chat_log_id: 9,
      hits_count: 1,
    };
    fetchMock.mockResolvedValue(jsonResponse(response));
    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /知识问答/ }));

    const input = screen.getByLabelText('法律问题');
    fireEvent.change(input, { target: { value: '产品缺陷造成损害怎么办' } });
    fireEvent.click(screen.getByRole('button', { name: '提交问题' }));
    expect(await screen.findByText('生产者')).toBeVisible();
    expect(screen.getAllByText('第一千二百零二条')[0]).toBeVisible();

    fireEvent.change(input, { target: { value: '再问一次' } });
    fireEvent.click(screen.getByRole('button', { name: '提交问题' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const bodies = fetchMock.mock.calls.map((call) =>
      JSON.parse(String(call[1]?.body)) as { session_id: string },
    );
    expect(bodies[0].session_id).toBe('session-one');
    expect(bodies[1].session_id).toBe('session-one');
  });

  it('creates a new session after the page is remounted', () => {
    const first = render(<App />);
    expect(mockedSessionId).toHaveBeenCalledTimes(1);
    first.unmount();
    render(<App />);
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
    render(<App />);
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
