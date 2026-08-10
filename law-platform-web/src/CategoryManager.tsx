import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ApiError,
  batchDeleteKnowledgeDocuments,
  batchMoveKnowledgeDocuments,
  createKnowledgeCategory,
  deactivateKnowledgeCategory,
  listKnowledgeCategories,
  listKnowledgeDocuments,
  updateKnowledgeCategory,
  updateKnowledgeDocumentCategory,
} from './api';
import CategoryCascadeSelect from './CategoryCascadeSelect';
import PageJump from './PageJump';
import { activeCategoryTree, categoryLabel, findCategory, flattenCategories } from './knowledgeCategories';
import type { KnowledgeCategoryNode, KnowledgeDocument } from './types';

const DEFAULT_PAGE_SIZE = 5;
const MAX_BATCH_SIZE = 100;
const pageSizeOptions = [5, 10, 20, 50, 100, 500, 1000] as const;

const statusLabels: Record<string, string> = {
  pending: '等待入库',
  processing: '正在入库',
  success: '入库成功',
  failed: '入库失败',
  skipped: '已存在',
};

interface EditorState {
  id: string | null;
  name: string;
  aliases: string;
  parentId: string;
  assignable: boolean;
  sensitive: boolean;
}

const emptyEditor: EditorState = {
  id: null,
  name: '',
  aliases: '',
  parentId: '',
  assignable: true,
  sensitive: false,
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '分类操作失败，请稍后重试';
}

function safePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function levelName(depth: number): string {
  const names = ['一级分类', '二级分类', '三级分类', '四级分类', '五级分类', '六级分类'];
  return names[depth - 1] ?? `第 ${depth} 级分类`;
}

function siblingsOf(
  categories: KnowledgeCategoryNode[],
  node: KnowledgeCategoryNode,
): KnowledgeCategoryNode[] {
  if (!node.parent_id) return categories;
  return findCategory(categories, node.parent_id)?.children ?? [];
}

function CategoryBadges({ node }: { node: KnowledgeCategoryNode }) {
  return (
    <div className="category-badges">
      {!node.assignable && <span>不可直接归档</span>}
      {node.effective_sensitive && <span>敏感</span>}
      {node.is_system && <span>系统</span>}
      {node.status === 'inactive' && <span>已停用</span>}
    </div>
  );
}

export default function CategoryManager() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState<KnowledgeCategoryNode[]>([]);
  const [selectedId, setSelectedId] = useState(searchParams.get('category_id') ?? '');
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [busyId, setBusyId] = useState('');
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [documentTotal, setDocumentTotal] = useState(0);
  const [documentPage, setDocumentPage] = useState(safePage(searchParams.get('doc_page')));
  const [documentPageSize, setDocumentPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [documentKeyword, setDocumentKeyword] = useState('');
  const [documentStatus, setDocumentStatus] = useState('');
  const [appliedDocumentKeyword, setAppliedDocumentKeyword] = useState('');
  const [appliedDocumentStatus, setAppliedDocumentStatus] = useState('');
  const [filterCategoryId, setFilterCategoryId] = useState(searchParams.get('category_id') ?? '');
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [moveTarget, setMoveTarget] = useState<KnowledgeDocument | null>(null);
  const [moveCategoryId, setMoveCategoryId] = useState('');
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [batchMoveOpen, setBatchMoveOpen] = useState(false);
  const [batchCategoryId, setBatchCategoryId] = useState('');
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false);
  const [inactiveQuery, setInactiveQuery] = useState('');

  const flat = useMemo(() => flattenCategories(categories), [categories]);
  const activeCategories = useMemo(() => activeCategoryTree(categories), [categories]);
  const selected = findCategory(activeCategories, selectedId);
  const leftNodes = selected ? siblingsOf(activeCategories, selected) : activeCategories;
  const rightNodes = selected?.children ?? [];
  const breadcrumbNodes = selected
    ? selected.path_ids
        .map((id) => flat.find((node) => node.id === id))
        .filter((node): node is KnowledgeCategoryNode => Boolean(node))
    : [];
  const moveCategory = findCategory(categories, moveCategoryId);
  const selectedFilterCategory = findCategory(categories, filterCategoryId);
  const documentPageCount = Math.max(1, Math.ceil(documentTotal / documentPageSize));
  const batchCategory = findCategory(categories, batchCategoryId);
  const selectedCount = selectedDocIds.size;
  const allOnPageSelected = documents.length > 0 && documents.every((document) => selectedDocIds.has(document.doc_id));
  const inactiveCategories = useMemo(() => {
    const query = inactiveQuery.trim().toLocaleLowerCase('zh-CN');
    return flat
      .filter((node) => node.status === 'inactive')
      .filter((node) => !query || `${node.name} ${node.path.join(' / ')} ${node.aliases.join(' ')}`.toLocaleLowerCase('zh-CN').includes(query))
      .sort((a, b) => categoryLabel(a).localeCompare(categoryLabel(b), 'zh-CN'));
  }, [flat, inactiveQuery]);
  const inactiveTotal = flat.filter((node) => node.status === 'inactive').length;

  function syncUrl(categoryId: string, page: number) {
    const next = new URLSearchParams(searchParams);
    if (categoryId) next.set('category_id', categoryId);
    else next.delete('category_id');
    next.set('doc_page', String(page));
    setSearchParams(next, { replace: true });
  }

  async function loadCategories(preferredId = selectedId): Promise<string> {
    setLoadingCategories(true);
    try {
      const result = await listKnowledgeCategories(true);
      setCategories(result.items);
      const nextFlat = flattenCategories(result.items);
      const preferred = nextFlat.find((node) => node.id === preferredId);
      const nearestActiveId = preferred?.path_ids
        .slice()
        .reverse()
        .find((id) => nextFlat.some((node) => node.id === id && node.status === 'active'));
      const validId = preferred?.status === 'active'
        ? preferred.id
        : nearestActiveId ?? nextFlat.find((node) => node.status === 'active')?.id ?? '';
      setSelectedId(validId);
      setFilterCategoryId(validId);
      if (validId !== selectedId || searchParams.get('category_id') !== validId) {
        setDocumentPage(1);
        syncUrl(validId, 1);
      }
      return validId;
    } catch (loadError: unknown) {
      setError(errorMessage(loadError));
      return '';
    } finally {
      setLoadingCategories(false);
    }
  }

  async function loadDocuments(
    categoryId: string,
    targetPage = documentPage,
    targetPageSize = documentPageSize,
    keyword = appliedDocumentKeyword,
    status = appliedDocumentStatus,
  ) {
    if (!categoryId) {
      setDocuments([]);
      setDocumentTotal(0);
      return;
    }
    setLoadingDocuments(true);
    try {
      let result = await listKnowledgeDocuments({
        page: targetPage,
        pageSize: targetPageSize,
        categoryId,
        keyword,
        status,
      });
      const lastPage = Math.max(1, Math.ceil(result.total / targetPageSize));
      if (targetPage > lastPage) {
        result = await listKnowledgeDocuments({
          page: lastPage,
          pageSize: targetPageSize,
          categoryId,
          keyword,
          status,
        });
      }
      setDocuments(result.items);
      setDocumentTotal(result.total);
      setDocumentPage(result.page);
      if (result.page !== targetPage) syncUrl(categoryId, result.page);
    } catch (loadError: unknown) {
      setError(errorMessage(loadError));
    } finally {
      setLoadingDocuments(false);
    }
  }

  useEffect(() => {
    void loadCategories(searchParams.get('category_id') ?? '');
    // 首次进入页面解析一次 URL；后续选择由页面事件维护。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedId) void loadDocuments(selectedId, documentPage, documentPageSize);
    // 分类、页码、每页数量或已应用的筛选条件改变时重新加载当前分类子树文档。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, documentPage, documentPageSize, appliedDocumentKeyword, appliedDocumentStatus]);

  useEffect(() => {
    setSelectedDocIds(new Set());
  }, [selectedId, documentPage, documentPageSize, appliedDocumentKeyword, appliedDocumentStatus]);

  function selectCategory(categoryId: string) {
    setSelectedId(categoryId);
    setFilterCategoryId(categoryId);
    setDocumentPage(1);
    setNotice('');
    syncUrl(categoryId, 1);
  }

  function applyDocumentFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const filterCategory = findCategory(categories, filterCategoryId);
    if (!filterCategory || filterCategory.status !== 'active') {
      setError('请选择启用中的分类');
      return;
    }
    setError('');
    setSelectedId(filterCategory.id);
    setAppliedDocumentKeyword(documentKeyword.trim());
    setAppliedDocumentStatus(documentStatus);
    setDocumentPage(1);
    syncUrl(filterCategory.id, 1);
  }

  function openCreate(parentId = '') {
    setEditor({ ...emptyEditor, parentId });
    setError('');
  }

  function openEdit(node: KnowledgeCategoryNode) {
    setEditor({
      id: node.id,
      name: node.name,
      aliases: node.aliases.join('，'),
      parentId: node.parent_id ?? '',
      assignable: node.assignable,
      sensitive: node.sensitive,
    });
    setError('');
  }

  async function saveCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || !editor.name.trim() || busyId) return;
    setBusyId(editor.id ?? 'new');
    setError('');
    setNotice('');
    const aliases = editor.aliases
      .split(/[，,]/)
      .map((value) => value.trim())
      .filter(Boolean);
    try {
      const saved = editor.id
        ? await updateKnowledgeCategory(editor.id, {
            name: editor.name.trim(),
            aliases,
            parent_id: editor.parentId || null,
            assignable: editor.assignable,
            sensitive: editor.sensitive,
          })
        : await createKnowledgeCategory({
            name: editor.name,
            aliases,
            parentId: editor.parentId || null,
            assignable: editor.assignable,
            sensitive: editor.sensitive,
          });
      await loadCategories(saved.id);
      selectCategory(saved.id);
      setEditor(null);
      setNotice(`分类“${saved.path.join(' / ')}”已保存。`);
    } catch (saveError: unknown) {
      setError(errorMessage(saveError));
    } finally {
      setBusyId('');
    }
  }

  async function mutateCategory(node: KnowledgeCategoryNode, action: 'up' | 'down' | 'toggle') {
    setBusyId(node.id);
    setError('');
    setNotice('');
    try {
      if (action === 'toggle') {
        if (node.status === 'active') await deactivateKnowledgeCategory(node.id);
        else await updateKnowledgeCategory(node.id, { status: 'active' });
      } else {
        const siblings = siblingsOf(categories, node)
          .slice()
          .sort((a, b) => a.sort_order - b.sort_order || Number(a.id) - Number(b.id));
        const index = siblings.findIndex((item) => item.id === node.id);
        const other = siblings[action === 'up' ? index - 1 : index + 1];
        if (!other) return;
        await updateKnowledgeCategory(node.id, { sort_order: other.sort_order });
        await updateKnowledgeCategory(other.id, { sort_order: node.sort_order });
      }
      await loadCategories(node.id);
      setNotice(action === 'toggle' ? `分类“${node.name}”状态已更新。` : `分类“${node.name}”顺序已更新。`);
    } catch (mutationError: unknown) {
      setError(errorMessage(mutationError));
    } finally {
      setBusyId('');
    }
  }

  function openMove(document: KnowledgeDocument) {
    setMoveTarget(document);
    setMoveCategoryId(document.category_id);
    setError('');
  }

  async function moveDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!moveTarget || !moveCategory?.assignable || moveCategory.is_system || busyId) return;
    setBusyId(`document-${moveTarget.doc_id}`);
    setError('');
    setNotice('');
    try {
      const updated = await updateKnowledgeDocumentCategory({
        docId: moveTarget.doc_id,
        categoryId: moveCategory.id,
      });
      setMoveTarget(null);
      await loadCategories(selectedId);
      await loadDocuments(selectedId, documentPage, documentPageSize);
      setNotice(`《${updated.title}》已移动到“${updated.category_path.join(' / ')}”；未重新解析、生成向量或调用 Qwen。`);
    } catch (moveError: unknown) {
      setError(errorMessage(moveError));
    } finally {
      setBusyId('');
    }
  }

  function toggleSelectDocument(docId: string) {
    setSelectedDocIds((previous) => {
      const next = new Set(previous);
      if (next.has(docId)) {
        next.delete(docId);
        return next;
      }
      if (next.size >= MAX_BATCH_SIZE) {
        setError(`一次最多只能选择 ${MAX_BATCH_SIZE} 份文档`);
        return previous;
      }
      next.add(docId);
      return next;
    });
  }

  function toggleSelectAllOnPage() {
    if (allOnPageSelected) {
      setSelectedDocIds((previous) => {
        const next = new Set(previous);
        for (const document of documents) {
          next.delete(document.doc_id);
        }
        return next;
      });
      return;
    }
    const availableSlots = MAX_BATCH_SIZE - selectedDocIds.size;
    if (availableSlots <= 0) {
      setError(`一次最多只能选择 ${MAX_BATCH_SIZE} 份文档`);
      return;
    }
    const toAdd = documents.slice(0, availableSlots);
    if (documents.length > availableSlots) {
      setNotice(`已选满 ${MAX_BATCH_SIZE} 份上限，仅勾选本页前 ${availableSlots} 份`);
    }
    setSelectedDocIds((previous) => {
      const next = new Set(previous);
      for (const document of toAdd) {
        next.add(document.doc_id);
      }
      return next;
    });
  }

  function openBatchMove() {
    setBatchCategoryId('');
    setBatchMoveOpen(true);
    setError('');
  }

  async function submitBatchMove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedCount === 0 || !batchCategory?.assignable || batchCategory.is_system || busyId) return;
    setBusyId('batch-move');
    setError('');
    setNotice('');
    try {
      const result = await batchMoveKnowledgeDocuments({
        docIds: [...selectedDocIds],
        categoryId: batchCategory.id,
      });
      setBatchMoveOpen(false);
      setSelectedDocIds(new Set());
      await loadCategories(selectedId);
      await loadDocuments(selectedId, documentPage, documentPageSize);
      setNotice(`已批量移动 ${result.moved} 份文档到“${result.category_path.join(' / ')}”；未重新解析、生成向量或调用 Qwen。`);
    } catch (moveError: unknown) {
      setError(errorMessage(moveError));
    } finally {
      setBusyId('');
    }
  }

  function openBatchDelete() {
    setBatchDeleteOpen(true);
    setError('');
  }

  async function confirmBatchDelete() {
    if (selectedCount === 0 || busyId) return;
    setBusyId('batch-delete');
    setError('');
    setNotice('');
    try {
      const result = await batchDeleteKnowledgeDocuments([...selectedDocIds]);
      setBatchDeleteOpen(false);
      setSelectedDocIds(new Set());
      await loadCategories(selectedId);
      await loadDocuments(selectedId, documentPage, documentPageSize);
      setNotice(
        `已删除 ${result.deleted} 份文档，已移入回收站，可稍后恢复。`,
      );
    } catch (deleteError: unknown) {
      setError(errorMessage(deleteError));
    } finally {
      setBusyId('');
    }
  }

  const unavailableParents = new Set(
    editor?.id
      ? flat
          .filter((node) => node.id === editor.id || node.path_ids.includes(editor.id!))
          .map((node) => node.id)
      : [],
  );

  function renderCategoryCard(node: KnowledgeCategoryNode, isSelected: boolean) {
    return (
      <article className={`category-level-card status-${node.status}${isSelected ? ' is-selected' : ''}`} key={node.id}>
        <button className="category-level-select" type="button" onClick={() => selectCategory(node.id)}>
          <strong>{node.name}</strong>
          <small>直接 {node.direct_document_count} 份 · 含下级 {node.total_document_count} 份</small>
          {node.aliases.length > 0 && <small>别名：{node.aliases.join('、')}</small>}
          <CategoryBadges node={node} />
        </button>
        {!node.is_system && (
          <div className="category-row-actions">
            {node.status === 'active' && <button type="button" disabled={Boolean(busyId)} onClick={() => openCreate(node.id)}>新增下级</button>}
            <button type="button" disabled={Boolean(busyId)} onClick={() => openEdit(node)}>编辑</button>
            <button type="button" disabled={Boolean(busyId)} onClick={() => void mutateCategory(node, 'up')}>上移</button>
            <button type="button" disabled={Boolean(busyId)} onClick={() => void mutateCategory(node, 'down')}>下移</button>
            <button type="button" disabled={Boolean(busyId)} onClick={() => void mutateCategory(node, 'toggle')}>{node.status === 'active' ? '停用' : '启用'}</button>
          </div>
        )}
      </article>
    );
  }

  return (
    <section id="categories-panel" className="panel category-management-panel" aria-labelledby="categories-tab">
      <div className="panel-heading category-page-heading">
        <div>
          <p className="section-number">04 / CATEGORY</p>
          <h2>知识分类管理</h2>
        </div>
        <p>一级、二级及更深分类逐级分开展示。分类结构调整后，检索引用会立即使用最新路径。</p>
      </div>

      <div className="category-toolbar">
        <button className="primary-button" type="button" disabled={Boolean(busyId)} onClick={() => openCreate()}>新增一级分类</button>
        <button
          className="example-button"
          type="button"
          disabled={loadingCategories || loadingDocuments || Boolean(busyId)}
          onClick={() => void (async () => {
            const nextId = await loadCategories(selectedId);
            if (nextId) await loadDocuments(nextId, documentPage, documentPageSize);
          })()}
        >
          刷新分类与文档
        </button>
        <a className="document-action-link" href="/?tab=knowledge">返回知识库管理</a>
      </div>

      {notice && <div className="success-card" role="status">{notice}</div>}
      {error && <div className="error-card" role="alert">{error}</div>}
      <section className="active-categories-section" aria-labelledby="active-categories-title">
        <div className="category-section-heading">
          <div>
            <p className="section-number">ACTIVE CATEGORIES</p>
            <h3 id="active-categories-title">启用中的分类</h3>
          </div>
          <span>{flat.filter((node) => node.status === 'active').length} 个</span>
        </div>
        {loadingCategories && <div className="loading-card">正在加载分类树…</div>}

        {!loadingCategories && selected && (
          <>
          <nav className="category-breadcrumb" aria-label="分类路径">
            {breadcrumbNodes.map((node, index) => (
              <span key={node.id}>
                {index > 0 && <span aria-hidden="true">/</span>}
                <button type="button" onClick={() => selectCategory(node.id)} aria-current={node.id === selected.id ? 'page' : undefined}>{node.name}</button>
              </span>
            ))}
          </nav>

          <div className="category-level-browser">
            <section className="category-level-column" aria-labelledby="current-level-title">
              <div className="category-level-heading">
                <div>
                  <p className="section-number">CURRENT LEVEL</p>
                  <h3 id="current-level-title">{levelName(selected.depth)}</h3>
                </div>
                <span>{leftNodes.length} 个</span>
              </div>
              <div className="category-level-list">
                {leftNodes.map((node) => renderCategoryCard(node, node.id === selected.id))}
              </div>
            </section>

            <section className="category-level-column" aria-labelledby="next-level-title">
              <div className="category-level-heading">
                <div>
                  <p className="section-number">NEXT LEVEL</p>
                  <h3 id="next-level-title">{levelName(selected.depth + 1)}</h3>
                </div>
                <span>{rightNodes.length} 个</span>
              </div>
              {rightNodes.length > 0 ? (
                <div className="category-level-list">
                  {rightNodes.map((node) => renderCategoryCard(node, false))}
                </div>
              ) : (
                <div className="empty-card">当前分类暂无下级分类。</div>
              )}
            </section>
          </div>

          <section className="category-documents">
            <div className="results-summary">
              <div>
                <h3>当前分类及下级文档</h3>
                <small>{categoryLabel(selected)}</small>
              </div>
              <div className="list-summary-controls">
                <span>共 {documentTotal} 份</span>
                <label>
                  <span>每页显示</span>
                  <select
                    aria-label="分类文档每页数量"
                    value={documentPageSize}
                    disabled={loadingDocuments}
                    onChange={(event) => {
                      setDocumentPageSize(Number(event.target.value));
                      setDocumentPage(1);
                      syncUrl(selected.id, 1);
                    }}
                  >
                    {pageSizeOptions.map((value) => <option value={value} key={value}>{value} 份</option>)}
                  </select>
                </label>
              </div>
            </div>
            <form
              className="filter-bar knowledge-filter-bar category-document-filter"
              aria-label="分类文档筛选"
              onSubmit={applyDocumentFilters}
            >
              <input
                aria-label="按标题筛选"
                value={documentKeyword}
                onChange={(event) => setDocumentKeyword(event.target.value)}
                placeholder="按标题搜索"
              />
              <CategoryCascadeSelect
                categories={categories}
                value={filterCategoryId}
                onChange={setFilterCategoryId}
                ariaPrefix="筛选"
                includeSystem
                className="filter-category-cascade"
                showPath={false}
              />
              <select
                aria-label="按状态筛选"
                value={documentStatus}
                onChange={(event) => setDocumentStatus(event.target.value)}
              >
                <option value="">全部状态</option>
                <option value="pending">等待入库</option>
                <option value="processing">正在入库</option>
                <option value="success">入库成功</option>
                <option value="failed">入库失败</option>
                <option value="skipped">已存在</option>
              </select>
              <button className="example-button" type="submit" disabled={loadingDocuments}>筛选</button>
              {selectedFilterCategory && (
                <small className="category-filter-path">
                  当前路径：{selectedFilterCategory.path.join(' / ')}
                  {!selectedFilterCategory.assignable && ' · 请选择可直接归档的下级分类'}
                </small>
              )}
            </form>
            {!loadingDocuments && documents.length > 0 && (
              <div className="batch-actions-row" role="toolbar" aria-label="批量操作">
                <label className="document-select-row">
                  <input
                    type="checkbox"
                    checked={allOnPageSelected}
                    disabled={Boolean(busyId)}
                    onChange={toggleSelectAllOnPage}
                    aria-label="全选本页文档"
                  />
                  <span>全选本页</span>
                </label>
                <span className="batch-selected-count">已选 {selectedCount} 份</span>
                <div className="batch-actions-buttons">
                  <button
                    type="button"
                    className="primary-button"
                    disabled={selectedCount === 0 || Boolean(busyId)}
                    onClick={openBatchMove}
                  >
                    批量移动
                  </button>
                  <button
                    type="button"
                    className="danger-button"
                    disabled={selectedCount === 0 || Boolean(busyId)}
                    onClick={openBatchDelete}
                  >
                    批量删除
                  </button>
                  <button
                    type="button"
                    disabled={selectedCount === 0 || Boolean(busyId)}
                    onClick={() => setSelectedDocIds(new Set())}
                  >
                    清除选择
                  </button>
                </div>
              </div>
            )}
            {loadingDocuments && <div className="loading-card">正在加载当前分类文档…</div>}
            {!loadingDocuments && documents.length === 0 && <div className="empty-card">当前分类及下级分类暂无文档。</div>}
            {!loadingDocuments && documents.length > 0 && (
              <div className="category-document-list">
                {documents.map((document) => (
                  <article className="category-document-card" key={document.doc_id}>
                    <label className="document-select-row">
                      <input
                        type="checkbox"
                        checked={selectedDocIds.has(document.doc_id)}
                        disabled={Boolean(busyId) || (!selectedDocIds.has(document.doc_id) && selectedCount >= MAX_BATCH_SIZE)}
                        onChange={() => toggleSelectDocument(document.doc_id)}
                        aria-label={`选择《${document.title}》`}
                      />
                    </label>
                    <div>
                      <div className="document-title-row">
                        <h4>{document.title}</h4>
                        <span className={`status-pill status-${document.embedding_status}`}>{statusLabels[document.embedding_status] ?? document.embedding_status}</span>
                      </div>
                      <p>{document.category_path.join(' / ')}</p>
                      <small>文档 #{document.doc_id} · {document.source_count} 个源文件</small>
                    </div>
                    <button type="button" disabled={Boolean(busyId)} onClick={() => openMove(document)}>移动到其他分类</button>
                  </article>
                ))}
              </div>
            )}
            <div className="pagination">
              <button type="button" disabled={documentPage <= 1 || loadingDocuments} onClick={() => { const next = documentPage - 1; setDocumentPage(next); syncUrl(selected.id, next); }}>上一页</button>
              <span>第 {documentPage} / {documentPageCount} 页</span>
              <button type="button" disabled={documentPage >= documentPageCount || loadingDocuments} onClick={() => { const next = documentPage + 1; setDocumentPage(next); syncUrl(selected.id, next); }}>下一页</button>
              <PageJump pageCount={documentPageCount} disabled={loadingDocuments} onJump={(target) => { setDocumentPage(target); syncUrl(selected.id, target); }} />
            </div>
          </section>
          </>
        )}
        {!loadingCategories && !selected && <div className="empty-card">暂无启用中的分类。</div>}
      </section>

      <section className="inactive-categories-section" aria-labelledby="inactive-categories-title">
        <div className="category-section-heading">
          <div>
            <p className="section-number">INACTIVE CATEGORIES</p>
            <h3 id="inactive-categories-title">已停用分类</h3>
          </div>
          <span>共 {inactiveTotal} 个</span>
        </div>
        <label className="inactive-category-search">
          <span>搜索停用分类</span>
          <input
            type="search"
            value={inactiveQuery}
            placeholder="按名称、完整路径或别名搜索"
            onChange={(event) => setInactiveQuery(event.target.value)}
          />
        </label>
        {!loadingCategories && inactiveCategories.length === 0 && (
          <div className="empty-card">{inactiveQuery.trim() ? '没有匹配的停用分类。' : '暂无已停用分类。'}</div>
        )}
        {!loadingCategories && inactiveCategories.length > 0 && (
          <div className="inactive-category-list">
            {inactiveCategories.map((node) => (
              <article className="inactive-category-card" key={node.id}>
                <div>
                  <div className="document-title-row">
                    <h4>{node.name}</h4>
                    <span className="status-pill status-inactive">已停用</span>
                  </div>
                  <p>{categoryLabel(node)}</p>
                  <small>
                    原层级：{levelName(node.depth)}
                    {node.aliases.length > 0 ? ` · 别名：${node.aliases.join('、')}` : ''}
                  </small>
                </div>
                <button
                  type="button"
                  disabled={Boolean(busyId)}
                  onClick={() => void mutateCategory(node, 'toggle')}
                >
                  {busyId === node.id ? '正在启用…' : '重新启用'}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {editor && (
        <div className="replace-modal-backdrop" role="presentation">
          <section className="replace-modal" role="dialog" aria-modal="true" aria-labelledby="category-editor-title">
            <div className="results-summary">
              <div>
                <p className="section-number">CATEGORY EDITOR</p>
                <h3 id="category-editor-title">{editor.id ? '编辑分类' : editor.parentId ? '新增下级分类' : '新增一级分类'}</h3>
              </div>
              <button type="button" disabled={Boolean(busyId)} onClick={() => setEditor(null)}>关闭</button>
            </div>
            <form className="category-editor-form" onSubmit={saveCategory}>
              <label><span>分类名称</span><input aria-label="分类名称" maxLength={100} value={editor.name} onChange={(event) => setEditor({ ...editor, name: event.target.value })} /></label>
              <label><span>别名（逗号分隔）</span><input aria-label="分类别名" value={editor.aliases} onChange={(event) => setEditor({ ...editor, aliases: event.target.value })} /></label>
              <CategoryCascadeSelect
                categories={categories}
                value={editor.parentId}
                onChange={(parentId) => setEditor({ ...editor, parentId })}
                ariaPrefix="父分类"
                allowEmpty
                emptyLabel="作为一级分类"
                excludedIds={unavailableParents}
                className="editor-parent-cascade"
              />
              <label className="confirmation-row"><input type="checkbox" checked={editor.assignable} onChange={(event) => setEditor({ ...editor, assignable: event.target.checked })} />允许直接归档文档</label>
              <label className="confirmation-row"><input type="checkbox" checked={editor.sensitive} onChange={(event) => setEditor({ ...editor, sensitive: event.target.checked })} />标记为敏感分类</label>
              <div className="replace-modal-actions">
                <button type="button" disabled={Boolean(busyId)} onClick={() => setEditor(null)}>取消</button>
                <button className="primary-button" type="submit" disabled={!editor.name.trim() || Boolean(busyId)}>{busyId ? '正在保存…' : '保存分类'}</button>
              </div>
            </form>
          </section>
        </div>
      )}

      {moveTarget && (
        <div className="replace-modal-backdrop" role="presentation">
          <section className="replace-modal" role="dialog" aria-modal="true" aria-labelledby="move-document-title">
            <div className="results-summary">
              <div>
                <p className="section-number">MOVE DOCUMENT</p>
                <h3 id="move-document-title">移动《{moveTarget.title}》</h3>
              </div>
              <button type="button" disabled={Boolean(busyId)} onClick={() => setMoveTarget(null)}>关闭</button>
            </div>
            <p className="replace-safety-note">只更新数据库分类，不重新解析、不生成向量，也不会调用 Qwen。</p>
            {error && <div className="error-card" role="alert">{error}</div>}
            <form onSubmit={moveDocument}>
              <CategoryCascadeSelect
                categories={categories}
                value={moveCategoryId}
                onChange={setMoveCategoryId}
                ariaPrefix="目标"
                emptyLabel="请选择一级分类"
              />
              <div className="replace-modal-actions">
                <button type="button" disabled={Boolean(busyId)} onClick={() => setMoveTarget(null)}>取消</button>
                <button className="primary-button" type="submit" disabled={!moveCategory?.assignable || moveCategory.is_system || Boolean(busyId)}>{busyId ? '正在保存…' : '确认移动分类'}</button>
              </div>
            </form>
          </section>
        </div>
      )}

      {batchMoveOpen && (
        <div className="replace-modal-backdrop" role="presentation">
          <section className="replace-modal" role="dialog" aria-modal="true" aria-labelledby="batch-move-title">
            <div className="results-summary">
              <div>
                <p className="section-number">BATCH MOVE</p>
                <h3 id="batch-move-title">批量移动 {selectedCount} 份文档</h3>
              </div>
              <button type="button" disabled={Boolean(busyId)} onClick={() => setBatchMoveOpen(false)}>关闭</button>
            </div>
            <p className="replace-safety-note">只更新数据库分类，不重新解析、不生成向量，也不会调用 Qwen。</p>
            {error && <div className="error-card" role="alert">{error}</div>}
            <form onSubmit={submitBatchMove}>
              <CategoryCascadeSelect
                categories={categories}
                value={batchCategoryId}
                onChange={setBatchCategoryId}
                ariaPrefix="目标"
                emptyLabel="请选择一级分类"
              />
              <div className="replace-modal-actions">
                <button type="button" disabled={Boolean(busyId)} onClick={() => setBatchMoveOpen(false)}>取消</button>
                <button className="primary-button" type="submit" disabled={!batchCategory?.assignable || batchCategory.is_system || Boolean(busyId)}>{busyId ? '正在保存…' : '确认批量移动'}</button>
              </div>
            </form>
          </section>
        </div>
      )}

      {batchDeleteOpen && (
        <div className="replace-modal-backdrop" role="presentation">
          <section className="replace-modal" role="dialog" aria-modal="true" aria-labelledby="batch-delete-title">
            <div className="results-summary">
              <div>
                <p className="section-number">BATCH DELETE</p>
                <h3 id="batch-delete-title">确认删除 {selectedCount} 份文档？</h3>
              </div>
              <button type="button" disabled={Boolean(busyId)} onClick={() => setBatchDeleteOpen(false)}>关闭</button>
            </div>
            <p className="replace-safety-note">
              删除为软删除：文档会移入回收站，可稍后恢复。原件、向量、图片均保留，不会重新解析或重新嵌入；检索与问答不再命中。
            </p>
            {error && <div className="error-card" role="alert">{error}</div>}
            <div className="replace-modal-actions">
              <button type="button" disabled={Boolean(busyId)} onClick={() => setBatchDeleteOpen(false)}>取消</button>
              <button className="danger-button" type="button" disabled={Boolean(busyId)} onClick={() => void confirmBatchDelete()}>{busyId ? '正在删除…' : '确认删除'}</button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
