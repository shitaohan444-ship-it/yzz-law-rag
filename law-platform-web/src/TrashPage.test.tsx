import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TrashPage from './TrashPage';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const law = {
  id: '2', code: 'legal_law', name: '法律', aliases: [], parent_id: '1',
  path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2,
  sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0,
  children: [],
};

const legal = {
  id: '1', code: 'legal', name: '法律法规', aliases: [], parent_id: null,
  path: ['法律法规'], path_ids: ['1'], depth: 1, sort_order: 10,
  assignable: false, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0,
  children: [law],
};

const categoryTree = { items: [legal] };

function trashDoc(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    doc_id: '40',
    attachment_id: '60',
    title: '已删除的法规',
    category_id: '2',
    category_name: '法律',
    category_path: ['法律法规', '法律'],
    category_path_ids: ['1', '2'],
    category_valid: true,
    restorable: true,
    deleted_at: '2026-07-19T03:30:00Z',
    embedding_status: 'success',
    file_name: 'old.md',
    file_size: '128',
    source_count: 1,
    ...overrides,
  };
}

describe('TrashPage', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function mockTrashList(doc = trashDoc()) {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories'))
        return jsonResponse(categoryTree);
      if (url.startsWith('/api/rag/documents/trash'))
        return jsonResponse({ items: [doc], total: 1, page: 1, page_size: 10 });
      throw new Error(`unexpected request: ${url}`);
    });
  }

  it('renders the trash list with original category and deleted time', async () => {
    mockTrashList();
    render(<TrashPage />);

    const title = await screen.findByText('已删除的法规');
    expect(title).toBeVisible();
    const row = title.closest('.trash-row') as HTMLElement;
    expect(within(row).getByText(/法律法规 \/ 法律/)).toBeVisible();
    expect(within(row).getByText(/删除于/)).toBeVisible();
  });

  it('restores selected docs via POST /api/rag/documents/batch-restore', async () => {
    let restoreBody = '';
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url.startsWith('/api/rag/documents/trash'))
        return jsonResponse({ items: [trashDoc()], total: 1, page: 1, page_size: 10 });
      if (url === '/api/rag/documents/batch-restore' && init?.method === 'POST') {
        restoreBody = String(init.body);
        return jsonResponse({ restored: 1, doc_ids: ['40'] });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    render(<TrashPage />);

    expect(await screen.findByText('已删除的法规')).toBeVisible();
    fireEvent.click(screen.getByRole('checkbox', { name: /^选择《/ }));
    fireEvent.click(screen.getByRole('button', { name: '批量恢复' }));
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }));

    expect(await screen.findByText(/已恢复 1 份文档/)).toBeVisible();
    expect(JSON.parse(restoreBody)).toEqual({ doc_ids: ['40'] });
  });

  it('requires a new category before restoring a doc whose category lapsed', async () => {
    mockTrashList(trashDoc({ category_valid: false, restorable: false, category_path: ['已停用资料'] }));
    render(<TrashPage />);

    expect(await screen.findByText('已删除的法规')).toBeVisible();
    fireEvent.click(screen.getByRole('checkbox', { name: /^选择《/ }));
    fireEvent.click(screen.getByRole('button', { name: '批量恢复' }));

    // 原分类失效时，恢复弹窗要求选新分类，确认按钮在选出可归档分类前禁用
    expect(await screen.findByText(/请为每份选择新的可归档分类/)).toBeVisible();
    expect(screen.getByRole('button', { name: '确认恢复' })).toBeDisabled();
  });

  it('purges selected docs via POST /api/rag/documents/batch-purge after confirmation', async () => {
    let purgeBody = '';
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/rag/categories')) return jsonResponse(categoryTree);
      if (url.startsWith('/api/rag/documents/trash'))
        return jsonResponse({ items: [trashDoc()], total: 1, page: 1, page_size: 10 });
      if (url === '/api/rag/documents/batch-purge' && init?.method === 'POST') {
        purgeBody = String(init.body);
        return jsonResponse({ purged: 1, already_purged: 0 });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    render(<TrashPage />);

    expect(await screen.findByText('已删除的法规')).toBeVisible();
    fireEvent.click(screen.getByRole('checkbox', { name: /^选择《/ }));
    fireEvent.click(screen.getByRole('button', { name: '批量彻底删除' }));

    // 高风险二次确认：未勾选时禁用
    expect(screen.getByRole('button', { name: '确认彻底删除' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: '确认永久删除' }));
    fireEvent.click(screen.getByRole('button', { name: '确认彻底删除' }));

    expect(await screen.findByText(/已彻底删除 1 份文档/)).toBeVisible();
    expect(JSON.parse(purgeBody)).toEqual({ doc_ids: ['40'] });
  });
});
