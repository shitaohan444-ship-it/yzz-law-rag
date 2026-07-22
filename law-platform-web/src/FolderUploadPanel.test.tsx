import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import FolderUploadPanel from './FolderUploadPanel';
import type { KnowledgeCategoryNode } from './types';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeFile(name: string, rel: string, contents = 'x'): File {
  const file = new File([contents], name, { lastModified: 1 });
  Object.defineProperty(file, 'webkitRelativePath', { value: rel, configurable: true });
  return file;
}

function setInputFiles(input: HTMLElement, files: File[]): void {
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  Object.defineProperty(input, 'value', { value: files.length ? 'fake' : '', configurable: true });
  fireEvent.change(input);
}

const category: KnowledgeCategoryNode = {
  id: '2', name: '法律', code: 'legal_law', aliases: [], parent_id: '1',
  path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2, sort_order: 1,
  assignable: true, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0, children: [],
};

describe('FolderUploadPanel', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('lists accepted docs from the chosen folder and skips temp/non-doc files', () => {
    render(
      <FolderUploadPanel
        categories={[category]}
        categoryId="2"
        onCategoryChange={() => undefined}
        disabled={false}
        onBusyChange={() => undefined}
        onDocumentsChanged={async () => undefined}
        onCategoryInvalid={async () => undefined}
      />,
    );
    const input = screen.getByLabelText('选择本机文件夹');
    setInputFiles(input, [
      makeFile('a.docx', '我的文件夹/a.docx'),
      makeFile('notes.md', '我的文件夹/notes.md'),
      makeFile('~$tmp.docx', '我的文件夹/~$tmp.docx'), // Office 临时文件，应跳过
      makeFile('readme', '我的文件夹/readme'), // 无扩展名，应跳过
    ]);
    expect(screen.getByText(/2 \/ 500 个文件/)).toBeVisible();
    expect(screen.getByText(/我的文件夹\/a\.docx/)).toBeVisible();
    expect(screen.getByText(/我的文件夹\/notes\.md/)).toBeVisible();
    expect(screen.queryByText(/~\$tmp\.docx/)).toBeNull();
  });

  it('uploads each file with its REAL current name and ingests sequentially', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const method = (init as RequestInit | undefined)?.method;
      if (url === '/api/rag/documents' && method === 'POST') {
        const body = (init as RequestInit).body as FormData;
        const title = String(body.get('title'));
        // 标题 = 真实文件名去扩展名；文件名字段保留真实名
        return jsonResponse({
          document: { doc_id: title === '民法典片段' ? '1' : '2', doc_title: title },
          deduplicated: false,
        });
      }
      if (url.includes('/ingest') && method === 'POST') {
        return jsonResponse({ status: 'success', chunk_count: 3 });
      }
      if (url.includes('/status') && method === 'GET') {
        return jsonResponse({ embedding_status: 'success', chunk_count: 3 });
      }
      return jsonResponse({});
    });

    render(
      <FolderUploadPanel
        categories={[category]}
        categoryId="2"
        onCategoryChange={() => undefined}
        disabled={false}
        onBusyChange={() => undefined}
        onDocumentsChanged={async () => undefined}
        onCategoryInvalid={async () => undefined}
      />,
    );
    setInputFiles(screen.getByLabelText('选择本机文件夹'), [
      makeFile('民法典片段.docx', '新版/民法典片段.docx'),
      makeFile('刑法片段.docx', '新版/刑法片段.docx'),
    ]);

    fireEvent.click(screen.getByRole('button', { name: '开始上传' }));

    await waitFor(() => expect(screen.getAllByText('入库成功').length).toBe(2));

    // 两次上传各调用一次 ingest，且文件名字段用的是真实当前名
    const uploads = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url) === '/api/rag/documents' && (init as RequestInit)?.method === 'POST',
    );
    expect(uploads).toHaveLength(2);
    expect(((uploads[0][1] as RequestInit).body as FormData).get('file')).toBeInstanceOf(File);
    expect(((uploads[0][1] as RequestInit).body as FormData).get('file')).toHaveProperty(
      'name',
      '民法典片段.docx',
    );
    const ingests = fetchMock.mock.calls.filter(([url]) => String(url).includes('/ingest'));
    expect(ingests).toHaveLength(2);
  });

  it('marks deduplicated files as existing and skips ingest', async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const method = (init as RequestInit | undefined)?.method;
      if (url === '/api/rag/documents' && method === 'POST') {
        return jsonResponse({ document: { doc_id: '9', doc_title: '已存在' }, deduplicated: true });
      }
      if (url.includes('/ingest') && method === 'POST') return jsonResponse({ status: 'success' });
      if (url.includes('/status') && method === 'GET') return jsonResponse({ embedding_status: 'success' });
      return jsonResponse({});
    });

    render(
      <FolderUploadPanel
        categories={[category]}
        categoryId="2"
        onCategoryChange={() => undefined}
        disabled={false}
        onBusyChange={() => undefined}
        onDocumentsChanged={async () => undefined}
        onCategoryInvalid={async () => undefined}
      />,
    );
    setInputFiles(screen.getByLabelText('选择本机文件夹'), [makeFile('已存在.docx', '夹/已存在.docx')]);
    fireEvent.click(screen.getByRole('button', { name: '开始上传' }));

    await waitFor(() => expect(screen.getByText('文件已存在')).toBeVisible());
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/ingest'))).toBe(false);
  });
});
