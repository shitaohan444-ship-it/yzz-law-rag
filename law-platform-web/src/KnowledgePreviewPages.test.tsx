import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ChunkPreviewPage, MarkdownPreviewPage } from './KnowledgePreviewPages';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const sources = [
  { source_id: '81', document_id: '24', attachment_id: '56', source_title: '主文件.md', file_name: 'main.md', file_size: '18', sort_order: 0, is_primary: true, ingest_status: 'success', chunk_count: 20, image_total: 0, upload_timings: null, ingest_timings: null },
  { source_id: '82', document_id: '24', attachment_id: '57', source_title: '后续文件.md', file_name: 'append.md', file_size: '20', sort_order: 1, is_primary: false, ingest_status: 'success', chunk_count: 1, image_total: 1, upload_timings: null, ingest_timings: null },
];

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="当前预览地址">{location.pathname}{location.search}</output>;
}

function renderRoute(path: string, element: ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/knowledge/documents/:docId/markdown" element={element} />
        <Route path="/knowledge/documents/:docId/chunks" element={element} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe('knowledge preview pages', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('renders safe combined Markdown and updates source_id in the URL', async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/24/sources')) return jsonResponse({ items: sources });
      if (url.includes('/24/markdown')) {
        const selected = url.includes('source_id=82');
        return jsonResponse({
          doc_id: 24,
          doc_title: '预览测试文档',
          description_summary: null,
          image_count: selected ? 1 : 2,
          source_count: selected ? 1 : 2,
          source_id: selected ? 82 : null,
          markdown: selected ? '# 后续文件\n\n单来源正文' : '# 合并 Markdown\n\n![内部图片](http://127.0.0.1:9000/private)',
        });
      }
      throw new Error(`unexpected request: ${url}`);
    });

    renderRoute('/knowledge/documents/24/markdown', <MarkdownPreviewPage />);
    expect(await screen.findByText('合并 Markdown')).toBeVisible();
    expect(screen.getByRole('link', { name: '返回知识库管理' })).toHaveAttribute('href', '/?tab=knowledge');
    expect(screen.getByText('[文档图片已解析，预览中不直接访问 MinIO]')).toBeVisible();
    expect(screen.getByText(/2 个来源/)).toBeVisible();
    fireEvent.change(screen.getByLabelText('Markdown 来源筛选'), { target: { value: '82' } });
    expect(await screen.findByText('单来源正文')).toBeVisible();
    expect(screen.getByLabelText('当前预览地址')).toHaveTextContent('?source_id=82');
  });

  it('restores Chunk source and page from the URL and paginates with page_size 20', async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/24/sources')) return jsonResponse({ items: sources });
      if (url.includes('/24/chunks?')) {
        const parsed = new URL(url, 'http://localhost');
        const page = Number(parsed.searchParams.get('page'));
        expect(parsed.searchParams.get('page_size')).toBe('20');
        expect(parsed.searchParams.get('source_id')).toBe('82');
        return jsonResponse({
          doc_id: 24,
          doc_title: '预览测试文档',
          total: 21,
          page,
          page_size: 20,
          items: [{ chunk_id: `24:s:82:m:${page === 2 ? '0020' : '0000'}`, chunk_idx: page === 2 ? 20 : 0, text: '完整 Chunk 正文', char_count: 10, source: '法规', source_id: 82, source_title: '后续文件.md', source_file_name: 'append.md', source_chunk_idx: page === 2 ? 20 : 0, article_no: '第二十条', chapter: '第一章', content_type: 'markdown', image_id: null, page_no: 3, image_category: null }],
        });
      }
      throw new Error(`unexpected request: ${url}`);
    });

    renderRoute('/knowledge/documents/24/chunks?source_id=82&page=2', <ChunkPreviewPage />);
    expect(await screen.findByText('24:s:82:m:0020')).toBeVisible();
    expect(screen.getByText('来源内序号 20')).toBeVisible();
    expect(screen.getByText('第 2 / 2 页')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '上一页' }));
    expect(await screen.findByText('24:s:82:m:0000')).toBeVisible();
    expect(screen.getByLabelText('当前预览地址')).toHaveTextContent('source_id=82&page=1');
  });

  it('shows a safe Markdown not-found message', async () => {
    fetchMock.mockImplementation(async (input) => {
      if (String(input).endsWith('/404/sources')) return jsonResponse({ items: [] });
      return jsonResponse({ message: 'kb_document not found' }, 404);
    });
    renderRoute('/knowledge/documents/404/markdown', <MarkdownPreviewPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('文档或来源不存在');
  });

  it('shows a safe Chunk upstream error', async () => {
    fetchMock.mockImplementation(async (input) => {
      if (String(input).endsWith('/24/sources')) return jsonResponse({ items: sources });
      return jsonResponse({ message: 'chunk service unavailable' }, 502);
    });
    renderRoute('/knowledge/documents/24/chunks?page=1', <ChunkPreviewPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Chunk 服务暂时不可用');
  });
});
