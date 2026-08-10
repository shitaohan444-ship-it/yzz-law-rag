import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import KnowledgePanel from './KnowledgePanel';
import { UploadActivityProvider } from './UploadActivityContext';
import { FAILURE_DELAY_STORAGE_KEY } from './batchUploadUtils';

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
  category_id: '2',
  category_name: '法律',
  category_path: ['法律法规', '法律'],
  category_path_ids: ['1', '2'],
  category_sensitive: true,
  embedding_status: 'success',
  file_name: 'test.md',
  file_size: '18',
  source_count: 1,
  image_total: 0,
  created_at: '2026-07-16T00:00:00.000Z',
  last_uploaded_at: '2026-07-16T01:00:00.000Z',
  upload_timings: null,
  ingest_timings: null,
};

const categoryTree = {
  items: [
    {
      id: '1', code: 'legal', name: '法律法规', aliases: [], parent_id: null,
      path: ['法律法规'], path_ids: ['1'], depth: 1, sort_order: 10,
      assignable: false, sensitive: false, effective_sensitive: false,
      is_system: false, status: 'active', direct_document_count: 0,
      total_document_count: 1,
      children: [
        {
          id: '2', code: 'legal_law', name: '法律', aliases: [], parent_id: '1',
          path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2,
          sort_order: 20, assignable: true, sensitive: true,
          effective_sensitive: true, is_system: false, status: 'active',
          direct_document_count: 1, total_document_count: 1, children: [
            {
              id: '3', code: 'labor_law', name: '劳动法律', aliases: [], parent_id: '2',
              path: ['法律法规', '法律', '劳动法律'], path_ids: ['1', '2', '3'], depth: 3,
              sort_order: 10, assignable: true, sensitive: false,
              effective_sensitive: false, is_system: false, status: 'active',
              direct_document_count: 0, total_document_count: 0, children: [],
            },
            {
              id: '4', code: 'inactive_law', name: '停用法规', aliases: [], parent_id: '2',
              path: ['法律法规', '法律', '停用法规'], path_ids: ['1', '2', '4'], depth: 3,
              sort_order: 20, assignable: true, sensitive: false,
              effective_sensitive: false, is_system: false, status: 'inactive',
              direct_document_count: 0, total_document_count: 0, children: [],
            },
          ],
        },
      ],
    },
  ],
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
  uploaded_at: '2026-07-16T01:00:00.000Z',
  upload_timings: null,
  ingest_timings: null,
};

describe('KnowledgePanel', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('uses the top form only for new documents and removes the misleading continue button', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, page: 1, page_size: 5 }));
    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
    expect(await screen.findByRole('button', { name: '新建并自动入库' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '继续上传' })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '批量导入' })).toBeVisible();
  });

  it('imports multiple files sequentially with complete filenames as titles', async () => {
    const first = { ...documentItem, doc_id: '31', attachment_id: '61', title: '第一份.md', embedding_status: 'pending' };
    const duplicate = { ...documentItem, doc_id: '24', title: '已有文件.pdf' };
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url.startsWith('/api/rag/documents?')) return jsonResponse({ items: [], total: 0, page: 1, page_size: 5 });
      if (url === '/api/rag/documents' && init?.method === 'POST') {
        const body = init.body as FormData;
        const title = String(body.get('title'));
        return title === '第一份.md'
          ? jsonResponse({ document: first, deduplicated: false })
          : jsonResponse({ document: duplicate, deduplicated: true });
      }
      if (url.endsWith('/31/ingest?force=false')) {
        return jsonResponse({ doc_id: 31, status: 'success', chunk_count: 4, image_total: 0, image_kept: 0, image_filtered: 0, vl_status: 'success', message: '' });
      }
      if (url.endsWith('/31/status')) {
        return jsonResponse({ doc_id: 31, embedding_status: 'success', chunk_count: 4, doc_title: '第一份.md', vl_status: 'success', image_total: 0, image_kept: 0, image_filtered: 0, vl_processed_at: null });
      }
      throw new Error(`unexpected request: ${url}`);
    });

    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('tab', { name: '批量导入' }));
    const failureDelay = screen.getByLabelText('处理失败后等待时间');
    expect(within(failureDelay).getByRole('option', { name: '5秒' })).toBeVisible();
    expect(within(failureDelay).getByRole('option', { name: '30秒' })).toBeVisible();
    expect(within(failureDelay).getByRole('option', { name: '1分钟' })).toBeVisible();
    expect(within(failureDelay).getByRole('option', { name: '2分钟' })).toBeVisible();
    expect(within(failureDelay).getByRole('option', { name: '5分钟' })).toBeVisible();
    fireEvent.change(failureDelay, { target: { value: '30000' } });
    expect(localStorage.getItem(FAILURE_DELAY_STORAGE_KEY)).toBe('30000');

    const firstFile = new File(['one'], '第一份.md', { type: 'text/markdown' });
    const secondFile = new File(['two'], '已有文件.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('批量选择文件'), { target: { files: [firstFile, secondFile] } });
    expect(screen.getByText('第一份.md')).toBeVisible();
    expect(screen.getByText('已有文件.pdf')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '开始批量导入' }));

    await waitFor(() => expect(screen.getByText('入库成功')).toBeVisible());
    expect(screen.getByText('文件已存在')).toBeVisible();
    const uploadCalls = fetchMock.mock.calls.filter(
      ([url, request]) => String(url) === '/api/rag/documents' && request?.method === 'POST',
    );
    expect(uploadCalls).toHaveLength(2);
    expect((uploadCalls[0][1]?.body as FormData).get('title')).toBe('第一份.md');
    expect((uploadCalls[1][1]?.body as FormData).get('title')).toBe('已有文件.pdf');
    const ingestCallIndex = fetchMock.mock.calls.findIndex(([url]) => String(url).includes('/31/ingest'));
    const secondUploadIndex = fetchMock.mock.calls.findIndex(
      ([url, request]) => String(url) === '/api/rag/documents' && request?.method === 'POST' && (request.body as FormData).get('title') === '已有文件.pdf',
    );
    expect(ingestCallIndex).toBeLessThan(secondUploadIndex);
    expect(screen.getAllByRole('button', { name: '修改标题' })).toHaveLength(2);
  });

  it('edits a registered title without changing its last upload time or calling ingest', async () => {
    const updated = { ...documentItem, title: '修改后的标题' };
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url.startsWith('/api/rag/documents?')) return jsonResponse({ items: [documentItem], total: 1, page: 1, page_size: 5 });
      if (url.endsWith('/24/title') && init?.method === 'PATCH') return jsonResponse(updated);
      throw new Error(`unexpected request: ${url}`);
    });

    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
    expect(await screen.findByText('测试法规')).toBeVisible();
    expect(screen.getByText(/最后上传：/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '修改标题' }));
    fireEvent.change(screen.getByLabelText('修改后的文档标题'), { target: { value: '  修改后的标题  ' } });
    fireEvent.click(screen.getByRole('button', { name: '确认修改标题' }));

    expect(await screen.findByText('修改后的标题')).toBeVisible();
    const titleRequest = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/24/title'));
    expect(JSON.parse(String(titleRequest?.[1]?.body))).toEqual({ title: '修改后的标题' });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/ingest'))).toBe(false);
    expect(screen.getByText(/最后上传：/)).toBeVisible();
  });

  it('moves a registered document to another category without re-ingesting', async () => {
    const moved = {
      ...documentItem,
      category_id: '3',
      category_name: '劳动法律',
      category_path: ['法律法规', '法律', '劳动法律'],
      category_path_ids: ['1', '2', '3'],
    };
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url.startsWith('/api/rag/documents?')) return jsonResponse({ items: [documentItem], total: 1, page: 1, page_size: 5 });
      if (url.endsWith('/24/category') && init?.method === 'PATCH') return jsonResponse(moved);
      throw new Error(`unexpected request: ${url}`);
    });

    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
    expect(await screen.findByText('测试法规')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '移动到其他分类' }));
    fireEvent.change(screen.getByLabelText('目标三级分类'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: '确认移动分类' }));

    expect(await screen.findByText(/已移动到/)).toBeVisible();
    const moveRequest = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/24/category'));
    expect(moveRequest?.[1]?.method).toBe('PATCH');
    expect(JSON.parse(String(moveRequest?.[1]?.body))).toEqual({ category_id: '3' });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/ingest'))).toBe(false);
  });

  it('uses separate level selectors and contains no category-management actions', async () => {
    fetchMock.mockImplementation(async (input) => {
      if (String(input).startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      return jsonResponse({ items: [documentItem], total: 1, page: 1, page_size: 5 });
    });
    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);

    expect(await screen.findByLabelText('上传一级分类')).toHaveValue('1');
    expect(screen.getByLabelText('上传二级分类')).toHaveValue('2');
    expect(screen.getByLabelText('上传三级分类')).toHaveValue('');
    expect(within(screen.getByLabelText('上传三级分类')).getByRole('option', { name: '停用法规（已停用，不可选择）' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('筛选一级分类'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('筛选二级分类'), { target: { value: '2' } });
    expect(within(screen.getByLabelText('筛选三级分类')).getByRole('option', { name: '停用法规（已停用，不可选择）' })).toBeDisabled();
    expect(screen.getByText('当前路径：法律法规 / 法律', { selector: '.category-filter-path' })).toBeVisible();
    expect(screen.queryByText('停用分类不能用于上传、筛选或文档归类。')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '分类管理' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增分类' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '修改分类' })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('上传三级分类'), { target: { value: '3' } });
    expect(screen.getByText('当前路径：法律法规 / 法律 / 劳动法律')).toBeVisible();
    fireEvent.click(screen.getByRole('tab', { name: '批量导入' }));
    expect(within(screen.getByLabelText('批量上传三级分类')).getByRole('option', { name: '停用法规（已停用，不可选择）' })).toBeDisabled();
  });

  it('reuses a duplicate new-document upload and never calls the ingest endpoint', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
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

    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText('选择文件'), {
      target: { files: [new File(['# 测试法规'], 'test.md', { type: 'text/markdown' })] },
    });
    expect(screen.queryByText('我确认当前局域网使用者均可能检索此资料')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '新建并自动入库' }));

    expect(await screen.findByText(/该文件已存在/)).toBeVisible();
    expect(screen.getByText('测试法规')).toBeVisible();
    const uploadRequest = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === '/api/rag/documents' && init?.method === 'POST',
    );
    expect((uploadRequest?.[1]?.body as FormData).has('sensitive_confirmed')).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/ingest'))).toBe(false);
  });

  it('automatically ingests a new upload and displays the final chunk count', async () => {
    let uploaded = false;
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
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

    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
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
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url.startsWith('/api/rag/documents?')) return jsonResponse({ items: [timedDocument], total: 1, page: 1, page_size: 5 });
      throw new Error(`unexpected request: ${url}`);
    });

    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
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
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
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

    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
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
      if (String(input).startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      const url = new URL(String(input), 'http://localhost');
      const requestedPage = Number(url.searchParams.get('page'));
      const pageSize = Number(url.searchParams.get('page_size'));
      const offset = (requestedPage - 1) * pageSize;
      return jsonResponse({
        items: allDocuments.slice(offset, offset + pageSize),
        total: allDocuments.length,
        page: requestedPage,
        page_size: pageSize,
      });
    });

    render(<UploadActivityProvider><KnowledgePanel activeTab="knowledge" /></UploadActivityProvider>);
    expect(await screen.findByText('分页文档 1')).toBeVisible();
    expect(screen.getAllByRole('article')).toHaveLength(5);
    expect(screen.getByText('第 1 / 3 页')).toBeVisible();
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();
    const pageSizeSelect = screen.getByLabelText('已登记文档每页数量');
    expect(pageSizeSelect).toHaveValue('5');
    expect(screen.getAllByRole('option', { name: /份$/ }).map((option) => option.textContent)).toEqual([
      '5 份', '10 份', '20 份', '50 份', '100 份', '500 份', '1000 份',
    ]);

    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    expect(await screen.findByText('分页文档 6')).toBeVisible();
    expect(screen.getAllByRole('article')).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    expect(await screen.findByText('分页文档 11')).toBeVisible();
    expect(screen.getAllByRole('article')).toHaveLength(2);
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();

    fireEvent.change(pageSizeSelect, { target: { value: '10' } });
    expect(await screen.findByText('分页文档 1')).toBeVisible();
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(10));
    expect(screen.getByText('第 1 / 2 页')).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('page=1&page_size=10'))).toBe(true);

    fireEvent.change(pageSizeSelect, { target: { value: '1000' } });
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(12));
    expect(screen.getByText('第 1 / 1 页')).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('page=1&page_size=1000'))).toBe(true);

    fireEvent.change(screen.getByLabelText('按标题筛选'), { target: { value: '分页文档' } });
    fireEvent.click(screen.getByRole('button', { name: '筛选' }));
    expect(await screen.findByText('分页文档 1')).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('page=1&page_size=1000'))).toBe(true);
  });
});
