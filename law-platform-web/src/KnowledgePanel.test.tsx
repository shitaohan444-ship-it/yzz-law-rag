import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import KnowledgePanel from './KnowledgePanel';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const documentItem = {
  doc_id: '24',
  attachment_id: '56',
  title: '测试法规',
  category: '法规',
  embedding_status: 'success',
  file_name: 'test.md',
  file_size: '18',
  source_count: 1,
  image_total: 0,
  created_at: '2026-07-16T00:00:00.000Z',
  upload_timings: null,
  ingest_timings: null,
};

const primarySource = {
  source_id: '81',
  document_id: '24',
  attachment_id: '56',
  source_title: 'test.md',
  sort_order: 0,
  is_primary: true,
  ingest_status: 'success',
  chunk_count: 1,
  image_total: 0,
  image_kept: 0,
  image_filtered: 0,
  file_name: 'test.md',
  file_size: '18',
  upload_timings: null,
  ingest_timings: null,
};

describe('KnowledgePanel', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('uses the top form only for new documents and removes the misleading continue button', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, page: 1, page_size: 5 }));
    render(<KnowledgePanel />);
    expect(await screen.findByRole('button', { name: '新建并自动入库' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '继续上传' })).not.toBeInTheDocument();
  });

  it('reuses a duplicate new-document upload and never calls the ingest endpoint', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/documents?')) {
        const uploaded = fetchMock.mock.calls.some(
          ([calledUrl, calledInit]) =>
            String(calledUrl) === '/api/rag/documents' && calledInit?.method === 'POST',
        );
        return jsonResponse({ items: uploaded ? [documentItem] : [], total: uploaded ? 1 : 0, page: 1, page_size: 5 });
      }
      if (url === '/api/rag/documents' && init?.method === 'POST') {
        return jsonResponse({ document: documentItem, deduplicated: true });
      }
      throw new Error(`unexpected request: ${url}`);
    });

    render(<KnowledgePanel />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('选择文件'), {
      target: { files: [new File(['# 测试法规'], 'test.md', { type: 'text/markdown' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: '新建并自动入库' }));

    expect(await screen.findByText(/该文件已存在/)).toBeVisible();
    expect(screen.getByText('测试法规')).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/ingest'))).toBe(false);
  });

  it('automatically ingests a new upload and displays the final chunk count', async () => {
    let uploaded = false;
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/documents?')) {
        return jsonResponse({ items: uploaded ? [documentItem] : [], total: uploaded ? 1 : 0, page: 1, page_size: 5 });
      }
      if (url === '/api/rag/documents' && init?.method === 'POST') {
        uploaded = true;
        return jsonResponse({ document: { ...documentItem, embedding_status: 'pending' }, deduplicated: false });
      }
      if (url.endsWith('/ingest?force=false')) {
        return jsonResponse({ doc_id: 24, status: 'success', chunk_count: 6, image_total: 0, image_kept: 0, image_filtered: 0, vl_status: 'success', message: '' });
      }
      if (url.endsWith('/24/status')) {
        return jsonResponse({ doc_id: 24, embedding_status: 'success', chunk_count: 6, doc_title: '测试法规', vl_status: 'success', image_total: 0, image_kept: 0, image_filtered: 0, vl_processed_at: null });
      }
      throw new Error(`unexpected request: ${url}`);
    });

    render(<KnowledgePanel />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('选择文件'), {
      target: { files: [new File(['# 新法规'], 'test.md', { type: 'text/markdown' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: '新建并自动入库' }));

    expect(await screen.findByText(/已入库，共 6 个片段/)).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/ingest?force=false'))).toBe(true);
    expect(screen.getByRole('button', { name: '追加文件' })).toBeEnabled();
  });

  it('shows processing timings and opens previews through safe new-tab links', async () => {
    const timedDocument = {
      ...documentItem,
      upload_timings: { version: 1, status: 'success', started_at: '2026-07-16T00:00:00Z', completed_at: '2026-07-16T00:00:00Z', total_ms: 820.4, stages: [{ key: 'validate_hash', label: '文件校验与 SHA-256', elapsed_ms: 120.1, status: 'success' }] },
      ingest_timings: { version: 1, status: 'success', started_at: '2026-07-16T00:00:00Z', completed_at: '2026-07-16T00:00:08Z', total_ms: 8124.6, stages: [{ key: 'vl_analysis', label: '图片 VL 分析', elapsed_ms: 0, status: 'skipped' }] },
    };
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith('/api/rag/documents?')) return jsonResponse({ items: [timedDocument], total: 1, page: 1, page_size: 5 });
      throw new Error(`unexpected request: ${url}`);
    });

    render(<KnowledgePanel />);
    expect(await screen.findByText('测试法规')).toBeVisible();
    fireEvent.click(screen.getByText('处理耗时'));
    expect(screen.getByText('总耗时 820 毫秒')).toBeVisible();
    expect(screen.getByText('已跳过')).toBeVisible();

    const markdownLink = screen.getByRole('link', { name: '查看 Markdown' });
    const chunkLink = screen.getByRole('link', { name: '查看 Chunk' });
    expect(markdownLink).toHaveAttribute('href', '/knowledge/documents/24/markdown');
    expect(chunkLink).toHaveAttribute('href', '/knowledge/documents/24/chunks');
    expect(chunkLink).toHaveAttribute('target', '_blank');
    expect(chunkLink).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByLabelText('文档 Chunk 预览')).not.toBeInTheDocument();
  });

  it('appends a subsequent file to the same document and manages source-level replacement', async () => {
    const appended = { ...primarySource, source_id: '82', attachment_id: '57', source_title: '后续材料.md', sort_order: 1, is_primary: false, file_name: 'v2.md', chunk_count: 2 };
    let sourceItems = [primarySource];
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/documents?')) return jsonResponse({ items: [{ ...documentItem, source_count: sourceItems.length }], total: 1, page: 1, page_size: 5 });
      if (url.endsWith('/24/sources') && init?.method === 'POST') {
        sourceItems = [primarySource, appended];
        return jsonResponse({ document: { ...documentItem, source_count: 2 }, source: appended, chunk_count: 3 });
      }
      if (url.endsWith('/24/sources') && init?.method === 'GET') return jsonResponse({ items: sourceItems });
      if (url.endsWith('/24/sources/82/file') && init?.method === 'PUT') {
        sourceItems = [primarySource, { ...appended, source_title: '替换后来源.md', file_name: 'v3.md' }];
        return jsonResponse({ document: { ...documentItem, source_count: 2 }, source: sourceItems[1], chunk_count: 3 });
      }
      throw new Error(`unexpected request: ${url}`);
    });

    render(<KnowledgePanel />);
    expect(await screen.findByText('测试法规')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '追加文件' }));
    fireEvent.change(screen.getByLabelText('后续文件'), { target: { files: [new File(['v2'], 'v2.md', { type: 'text/markdown' })] } });
    expect(screen.getByLabelText('来源标题')).toHaveValue('v2.md');
    fireEvent.change(screen.getByLabelText('来源标题'), { target: { value: '后续材料.md' } });
    fireEvent.click(screen.getByRole('button', { name: '确认追加文件' }));
    expect(await screen.findByText(/当前共 2 个源文件、3 个 Chunk/)).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: '管理文件' }));
    expect(await screen.findByText('后续材料.md')).toBeVisible();
    const sourceMarkdownLinks = screen.getAllByRole('link', { name: '查看 Markdown' });
    const sourceChunkLinks = screen.getAllByRole('link', { name: '查看 Chunk' });
    expect(sourceMarkdownLinks[2]).toHaveAttribute('href', '/knowledge/documents/24/markdown?source_id=82');
    expect(sourceChunkLinks[2]).toHaveAttribute('href', '/knowledge/documents/24/chunks?source_id=82&page=1');
    const replaceButtons = screen.getAllByRole('button', { name: '替换文件' });
    fireEvent.click(replaceButtons[1]);
    expect(screen.getByLabelText('替换来源标题')).toHaveValue('后续材料.md');
    fireEvent.change(screen.getByLabelText('新的源文件'), { target: { files: [new File(['v3'], 'v3.md', { type: 'text/markdown' })] } });
    fireEvent.change(screen.getByLabelText('替换来源标题'), { target: { value: '替换后来源.md' } });
    fireEvent.click(screen.getByRole('button', { name: '确认替换源文件' }));
    expect(await screen.findByText('替换后来源.md')).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/24/sources/82/file'))).toBe(true);
  });

  it('shows registered documents five per page and resets filters to page one', async () => {
    const allDocuments = Array.from({ length: 12 }, (_, index) => ({
      ...documentItem,
      doc_id: String(index + 1),
      attachment_id: String(index + 101),
      title: `分页文档 ${index + 1}`,
    }));
    fetchMock.mockImplementation(async (input) => {
      const url = new URL(String(input), 'http://localhost');
      const requestedPage = Number(url.searchParams.get('page'));
      const pageSize = Number(url.searchParams.get('page_size'));
      expect(pageSize).toBe(5);
      const offset = (requestedPage - 1) * pageSize;
      return jsonResponse({
        items: allDocuments.slice(offset, offset + pageSize),
        total: allDocuments.length,
        page: requestedPage,
        page_size: pageSize,
      });
    });

    render(<KnowledgePanel />);
    expect(await screen.findByText('分页文档 1')).toBeVisible();
    expect(screen.getAllByRole('article')).toHaveLength(5);
    expect(screen.getByText('第 1 / 3 页')).toBeVisible();
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    expect(await screen.findByText('分页文档 6')).toBeVisible();
    expect(screen.getAllByRole('article')).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    expect(await screen.findByText('分页文档 11')).toBeVisible();
    expect(screen.getAllByRole('article')).toHaveLength(2);
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('按标题筛选'), { target: { value: '分页文档' } });
    fireEvent.click(screen.getByRole('button', { name: '筛选' }));
    expect(await screen.findByText('分页文档 1')).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('page=1&page_size=5'))).toBe(true);
  });
});
