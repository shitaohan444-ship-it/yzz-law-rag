import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CategoryManager from './CategoryManager';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const contract = {
  id: '4', code: 'labor_contract', name: '劳动合同', aliases: [], parent_id: '3',
  path: ['法律法规', '法律', '劳动法律', '劳动合同'], path_ids: ['1', '2', '3', '4'], depth: 4,
  sort_order: 10, assignable: true, sensitive: true, effective_sensitive: true,
  is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0, children: [],
};

const labor = {
  id: '3', code: 'labor_law', name: '劳动法律', aliases: [], parent_id: '2',
  path: ['法律法规', '法律', '劳动法律'], path_ids: ['1', '2', '3'], depth: 3,
  sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0,
  children: [contract],
};

const law = {
  id: '2', code: 'legal_law', name: '法律', aliases: [], parent_id: '1',
  path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2,
  sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0,
  children: [labor],
};

const inactiveArchive = {
  id: '8', code: 'inactive_archive', name: '已停用资料', aliases: ['旧资料'], parent_id: '1',
  path: ['法律法规', '已停用资料'], path_ids: ['1', '8'], depth: 2,
  sort_order: 20, assignable: true, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'inactive', direct_document_count: 0, total_document_count: 0,
  children: [],
};

const legal = {
  id: '1', code: 'legal', name: '法律法规', aliases: [], parent_id: null,
  path: ['法律法规'], path_ids: ['1'], depth: 1, sort_order: 10,
  assignable: false, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0,
  children: [law, inactiveArchive],
};

const pending = {
  id: '9', code: 'uncategorized', name: '待分类', aliases: [], parent_id: null,
  path: ['待分类'], path_ids: ['9'], depth: 1, sort_order: 999,
  assignable: false, sensitive: false, effective_sensitive: false,
  is_system: true, status: 'active', direct_document_count: 1, total_document_count: 1,
  children: [],
};

const categoryTree = { items: [legal, pending] };

const pendingDocument = {
  doc_id: '35', attachment_id: '56', title: '待整理文档', category: '待分类',
  category_id: '9', category_name: '待分类', category_path: ['待分类'], category_path_ids: ['9'],
  category_sensitive: false, embedding_status: 'success', file_name: 'pending.md', file_size: '18',
  source_count: 1, image_total: 0, created_at: '2026-07-17T00:00:00Z',
  upload_timings: null, ingest_timings: null,
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="当前地址">{location.pathname}{location.search}</output>;
}

function renderManager(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/knowledge/categories" element={<><CategoryManager /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CategoryManager', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('separates adjacent levels and restores deep navigation in the URL', async () => {
    fetchMock.mockImplementation(async (input) => {
      if (String(input).startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 5 });
    });
    renderManager('/knowledge/categories?category_id=1&doc_page=1');

    const firstLevel = await screen.findByRole('region', { name: '一级分类' });
    const secondLevel = screen.getByRole('region', { name: '二级分类' });
    expect(within(firstLevel).getByText('法律法规')).toBeVisible();
    expect(within(firstLevel).queryByText('法律')).not.toBeInTheDocument();
    expect(within(secondLevel).getByText('法律')).toBeVisible();
    expect(within(secondLevel).queryByText('法律法规')).not.toBeInTheDocument();

    fireEvent.click(within(secondLevel).getByRole('button', { name: /^法律/ }));
    expect(await screen.findByRole('region', { name: '三级分类' })).toHaveTextContent('劳动法律');
    fireEvent.click(within(screen.getByRole('region', { name: '三级分类' })).getByRole('button', { name: /^劳动法律/ }));
    expect(await screen.findByRole('region', { name: '四级分类' })).toHaveTextContent('劳动合同');
    expect(screen.getByLabelText('分类路径')).toHaveTextContent('法律法规/法律/劳动法律');
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('category_id=3');
  });

  it('keeps inactive categories out of the active levels and lists their full paths separately', async () => {
    fetchMock.mockImplementation(async (input) => {
      if (String(input).startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 5 });
    });
    renderManager('/knowledge/categories?category_id=1&doc_page=1');

    const activeSection = await screen.findByRole('region', { name: '启用中的分类' });
    const secondLevel = within(activeSection).getByRole('region', { name: '二级分类' });
    expect(within(secondLevel).queryByText('已停用资料')).not.toBeInTheDocument();

    const inactiveSection = screen.getByRole('region', { name: '已停用分类' });
    expect(within(inactiveSection).getByText('法律法规 / 已停用资料')).toBeVisible();
    expect(within(inactiveSection).getByText(/原层级：二级分类 · 别名：旧资料/)).toBeVisible();
    expect(within(inactiveSection).getByRole('button', { name: '重新启用' })).toBeEnabled();

    fireEvent.change(within(inactiveSection).getByRole('searchbox', { name: '搜索停用分类' }), { target: { value: '不存在' } });
    expect(within(inactiveSection).getByText('没有匹配的停用分类。')).toBeVisible();
  });

  it('re-enables an inactive category and moves it back into the active level', async () => {
    let enabled = false;
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const activeArchive = { ...inactiveArchive, status: 'active' };
      const currentTree = {
        items: [{ ...legal, children: [law, enabled ? activeArchive : inactiveArchive] }, pending],
      };
      if (url.startsWith('/api/rag/categories') && init?.method === 'PATCH') {
        enabled = true;
        return jsonResponse(activeArchive);
      }
      if (url.startsWith('/api/rag/categories')) return jsonResponse(currentTree);
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 5 });
    });
    renderManager('/knowledge/categories?category_id=1&doc_page=1');

    fireEvent.click(await screen.findByRole('button', { name: '重新启用' }));

    await waitFor(() => expect(screen.getByText('共 0 个')).toBeVisible());
    expect(screen.getByRole('region', { name: '二级分类' })).toHaveTextContent('已停用资料');
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith('/api/rag/categories/8') && init?.method === 'PATCH')).toBe(true);
  });

  it('moves a pending document with cascade selection and never calls an ingest endpoint', async () => {
    let moved = false;
    let patchBody = '';
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url.endsWith('/documents/35/category') && init?.method === 'PATCH') {
        moved = true;
        patchBody = String(init.body);
        return jsonResponse({
          ...pendingDocument,
          category_id: '2', category_name: '法律', category_path: ['法律法规', '法律'],
          category_path_ids: ['1', '2'],
        });
      }
      if (url.startsWith('/api/rag/documents?')) {
        return jsonResponse({ items: moved ? [] : [pendingDocument], total: moved ? 0 : 1, page: 1, page_size: 5 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    renderManager('/knowledge/categories?category_id=9&doc_page=1');

    expect(await screen.findByText('待整理文档')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '移动到其他分类' }));
    fireEvent.change(screen.getByLabelText('目标一级分类'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('目标二级分类'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '确认移动分类' }));

    expect(await screen.findByText(/未重新解析、生成向量或调用 Qwen/)).toBeVisible();
    expect(JSON.parse(patchBody)).toEqual({ category_id: '2' });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/ingest'))).toBe(false);
    await waitFor(() => expect(screen.queryByText('待整理文档')).not.toBeInTheDocument());
  });

  it('selects documents, selects all on page, and clears selection on category change', async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      return jsonResponse({
        items: [pendingDocument, { ...pendingDocument, doc_id: '36', title: '第二份文档' }],
        total: 2,
        page: 1,
        page_size: 5,
      });
    });
    renderManager('/knowledge/categories?category_id=9&doc_page=1');

    expect(await screen.findByText('待整理文档')).toBeVisible();
    expect(screen.getByText('已选 0 份')).toBeVisible();

    const checkboxes = screen.getAllByRole('checkbox', { name: /^选择《/ });
    expect(checkboxes).toHaveLength(2);

    fireEvent.click(checkboxes[0]);
    expect(screen.getByText('已选 1 份')).toBeVisible();

    fireEvent.click(screen.getByRole('checkbox', { name: '全选本页文档' }));
    expect(screen.getByText('已选 2 份')).toBeVisible();

    fireEvent.click(within(screen.getByRole('region', { name: '一级分类' })).getByRole('button', { name: /^法律法规/ }));
    expect(await screen.findByText('已选 0 份')).toBeVisible();
  });

  it('batch moves selected documents via POST /api/rag/documents/batch-move', async () => {
    let moveBody = '';
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url === '/api/rag/documents/batch-move' && init?.method === 'POST') {
        moveBody = String(init.body);
        return jsonResponse({ moved: 1, category_id: '2', category_path: ['法律法规', '法律'] });
      }
      if (url.startsWith('/api/rag/documents?')) {
        return jsonResponse({ items: [pendingDocument], total: 1, page: 1, page_size: 5 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    renderManager('/knowledge/categories?category_id=9&doc_page=1');

    expect(await screen.findByText('待整理文档')).toBeVisible();
    fireEvent.click(screen.getByRole('checkbox', { name: /^选择《/ }));
    fireEvent.click(screen.getByRole('button', { name: '批量移动' }));

    fireEvent.change(screen.getByLabelText('目标一级分类'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('目标二级分类'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '确认批量移动' }));

    expect(await screen.findByText(/已批量移动 1 份文档/)).toBeVisible();
    expect(JSON.parse(moveBody)).toEqual({ doc_ids: ['35'], category_id: '2' });
  });

  it('batch deletes selected documents via POST /api/rag/documents/batch-delete', async () => {
    let deleteBody = '';
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url === '/api/rag/documents/batch-delete' && init?.method === 'POST') {
        deleteBody = String(init.body);
        return jsonResponse({ deleted: 1, mode: 'soft', artifacts_retained: true });
      }
      if (url.startsWith('/api/rag/documents?')) {
        return jsonResponse({ items: [pendingDocument], total: 1, page: 1, page_size: 5 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    renderManager('/knowledge/categories?category_id=9&doc_page=1');

    expect(await screen.findByText('待整理文档')).toBeVisible();
    fireEvent.click(screen.getByRole('checkbox', { name: /^选择《/ }));
    fireEvent.click(screen.getByRole('button', { name: '批量删除' }));
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));

    expect(await screen.findByText(/已删除 1 份文档/)).toBeVisible();
    expect(JSON.parse(deleteBody)).toEqual({ doc_ids: ['35'] });
  });
});
