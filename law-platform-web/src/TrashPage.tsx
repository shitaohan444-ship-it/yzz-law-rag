import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ApiError,
  batchPurgeKnowledgeDocuments,
  batchRestoreKnowledgeDocuments,
  listKnowledgeCategories,
  listTrashDocuments,
} from './api';
import CategoryCascadeSelect from './CategoryCascadeSelect';
import PageJump from './PageJump';
import { flattenCategories } from './knowledgeCategories';
import type { KnowledgeCategoryNode, TrashDocument } from './types';

const DEFAULT_PAGE_SIZE = 10;
const MAX_BATCH_SIZE = 100;

const statusLabels: Record<string, string> = {
  pending: '等待入库',
  processing: '正在入库',
  success: '入库成功',
  failed: '入库失败',
  skipped: '已存在',
};

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '回收站操作失败';
}

function sizeLabel(value: string | null): string {
  if (!value) return '—';
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function dateTimeLabel(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

export default function TrashPage() {
  const [items, setItems] = useState<TrashDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(DEFAULT_PAGE_SIZE);
  const [keyword, setKeyword] = useState('');
  const [appliedKeyword, setAppliedKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [categories, setCategories] = useState<KnowledgeCategoryNode[]>([]);
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [restoreOverrides, setRestoreOverrides] = useState<Record<string, string>>({});
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [purgeConfirm, setPurgeConfirm] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(false);

  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const selectedCount = selectedDocIds.size;
  const allOnPageSelected = items.length > 0 && items.every((d) => selectedDocIds.has(d.doc_id));

  const loadCategories = useCallback(async () => {
    try {
      const tree = await listKnowledgeCategories(true);
      setCategories(tree.items);
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);

  const loadTrash = useCallback(
    async (targetPage: number, targetPageSize = pageSize) => {
      setLoadingList(true);
      setError(null);
      try {
        const lastPage = Math.max(1, Math.ceil(total / targetPageSize));
        const clamped = Math.min(Math.max(1, targetPage), lastPage);
        const result = await listTrashDocuments({
          page: clamped,
          pageSize: targetPageSize,
          categoryId: categoryFilter || undefined,
          keyword: appliedKeyword || undefined,
        });
        setItems(result.items);
        setTotal(result.total);
        setPage(result.page);
      } catch (err) {
        setError(messageOf(err));
      } finally {
        setLoadingList(false);
      }
    },
    [pageSize, total, categoryFilter, appliedKeyword],
  );

  useEffect(() => {
    void loadTrash(1);
    void loadCategories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyFilter = (event: React.FormEvent) => {
    event.preventDefault();
    setAppliedKeyword(keyword.trim());
    setSelectedDocIds(new Set());
    setPage(1);
    void loadTrash(1);
  };

  const resetFilter = () => {
    setKeyword('');
    setAppliedKeyword('');
    setCategoryFilter('');
    setSelectedDocIds(new Set());
    setPage(1);
    void loadTrash(1);
  };

  const toggleSelectDocument = (docId: string) => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else if (next.size < MAX_BATCH_SIZE) next.add(docId);
      return next;
    });
  };

  const toggleSelectAllOnPage = () => {
    setSelectedDocIds((prev) => {
      if (allOnPageSelected) {
        const next = new Set(prev);
        items.forEach((d) => next.delete(d.doc_id));
        return next;
      }
      const next = new Set(prev);
      for (const d of items) {
        if (next.size >= MAX_BATCH_SIZE) break;
        next.add(d.doc_id);
      }
      return next;
    });
  };

  const selectedItems = useMemo(
    () => items.filter((d) => selectedDocIds.has(d.doc_id)),
    [items, selectedDocIds],
  );
  const invalidCategoryDocs = selectedItems.filter((d) => !d.category_valid);
  const restoreReady =
    invalidCategoryDocs.every((d) => restoreOverrides[d.doc_id]) &&
    selectedCount > 0;

  const openRestore = () => {
    setRestoreOverrides({});
    setRestoreOpen(true);
    setError(null);
  };

  const confirmRestore = async (docIds: string[]) => {
    if (docIds.length === 0 || busyId) return;
    setBusyId(docIds.length > 1 ? 'batch-restore' : `restore-${docIds[0]}`);
    setError(null);
    try {
      const overrides = invalidCategoryDocs.reduce<Record<string, string>>(
        (acc, d) => {
          if (restoreOverrides[d.doc_id]) acc[d.doc_id] = restoreOverrides[d.doc_id];
          return acc;
        },
        {},
      );
      const result = await batchRestoreKnowledgeDocuments({
        docIds,
        categoryOverrides: Object.keys(overrides).length > 0 ? overrides : undefined,
      });
      setRestoreOpen(false);
      setSelectedDocIds(new Set());
      setNotice(`已恢复 ${result.restored} 份文档。`);
      await loadTrash(1);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusyId('');
    }
  };

  const openPurge = () => {
    setPurgeConfirm(false);
    setPurgeOpen(true);
    setError(null);
  };

  const confirmPurge = async (docIds: string[]) => {
    if (docIds.length === 0 || busyId) return;
    setBusyId(docIds.length > 1 ? 'batch-purge' : `purge-${docIds[0]}`);
    setError(null);
    try {
      const result = await batchPurgeKnowledgeDocuments(docIds);
      setPurgeOpen(false);
      setSelectedDocIds(new Set());
      const already = result.already_purged > 0 ? `（${result.already_purged} 份此前已彻底删除）` : '';
      setNotice(`已彻底删除 ${result.purged} 份文档${already}。`);
      await loadTrash(page);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusyId('');
    }
  };

  const flatCategories = useMemo(() => flattenCategories(categories), [categories]);

  return (
    <section className="panel trash-panel" aria-labelledby="trash-tab">
      <div className="panel-heading">
        <div>
          <p className="section-number">06 / RECYCLE BIN</p>
          <h2 id="trash-tab">回收站</h2>
          <p>已软删除的文档：原件、图片与向量仍保留，可恢复或永久删除。</p>
        </div>
      </div>

      {notice && (
        <div className="warning-card" role="status">
          {notice}
        </div>
      )}
      {error && (
        <div className="error-card" role="alert">
          {error}
        </div>
      )}

      <form className="filter-bar knowledge-filter-bar" onSubmit={applyFilter}>
        <label>
          <span>标题</span>
          <input
            aria-label="按标题搜索"
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="按标题搜索"
          />
        </label>
        <label>
          <span>原分类</span>
          <select
            aria-label="按原分类筛选"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="">全部分类</option>
            {flatCategories.map((node) => (
              <option key={node.id} value={node.id}>
                {node.path.join(' / ')}
                {node.status === 'inactive' ? '（已停用）' : ''}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="example-button">
          筛选
        </button>
        <button type="button" className="example-button" onClick={resetFilter}>
          重置
        </button>
      </form>

      <div
        className="batch-actions-row"
        role="toolbar"
        aria-label="回收站批量操作"
      >
        <label className="document-select-row">
          <input
            type="checkbox"
            checked={allOnPageSelected}
            disabled={Boolean(busyId) || loadingList}
            onChange={toggleSelectAllOnPage}
            aria-label="全选本页文档"
          />
        </label>
        <span className="batch-selected-count">已选 {selectedCount} 份</span>
        <div className="batch-actions-buttons">
          <button
            type="button"
            className="primary-button"
            disabled={selectedCount === 0 || Boolean(busyId)}
            onClick={openRestore}
          >
            批量恢复
          </button>
          <button
            type="button"
            className="danger-button"
            disabled={selectedCount === 0 || Boolean(busyId)}
            onClick={openPurge}
          >
            批量彻底删除
          </button>
          {selectedCount > 0 && (
            <button
              type="button"
              className="example-button"
              disabled={Boolean(busyId)}
              onClick={() => setSelectedDocIds(new Set())}
            >
              清除选择
            </button>
          )}
        </div>
      </div>

      <ul className="trash-list">
        {items.map((doc) => {
          const selected = selectedDocIds.has(doc.doc_id);
          return (
            <li key={doc.doc_id} className="trash-row">
              <label className="document-select-row">
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={
                    Boolean(busyId) ||
                    (!selected && selectedCount >= MAX_BATCH_SIZE)
                  }
                  onChange={() => toggleSelectDocument(doc.doc_id)}
                  aria-label={`选择《${doc.title}》`}
                />
              </label>
              <div className="trash-row-main">
                <h4>{doc.title}</h4>
                <p className="trash-row-meta">
                  <span className={`status-pill status-${doc.embedding_status}`}>
                    {statusLabels[doc.embedding_status] ?? doc.embedding_status}
                  </span>
                  {doc.file_name} · {sizeLabel(doc.file_size)} · {doc.source_count} 个源文件
                  {' · 删除于 '}
                  {dateTimeLabel(doc.deleted_at)}
                </p>
                <p className={`trash-row-category${doc.category_valid ? '' : ' invalid-category'}`}>
                  {doc.category_path && doc.category_path.length > 0
                    ? doc.category_path.join(' / ')
                    : '（无分类）'}
                  {!doc.category_valid && ' · 原分类已失效，恢复时需选择新分类'}
                </p>
              </div>
              <div className="document-actions">
                <button
                  type="button"
                  className="primary-button"
                  disabled={Boolean(busyId)}
                  onClick={() => {
                    setSelectedDocIds(new Set([doc.doc_id]));
                    setRestoreOverrides({});
                    setRestoreOpen(true);
                  }}
                >
                  恢复
                </button>
                <button
                  type="button"
                  className="danger-button"
                  disabled={Boolean(busyId)}
                  onClick={() => {
                    setSelectedDocIds(new Set([doc.doc_id]));
                    setPurgeConfirm(false);
                    setPurgeOpen(true);
                  }}
                >
                  彻底删除
                </button>
              </div>
            </li>
          );
        })}
        {items.length === 0 && !loadingList && (
          <li className="trash-empty">回收站为空。</li>
        )}
      </ul>

      <div className="pagination">
        <button
          type="button"
          onClick={() => {
            const next = Math.max(1, page - 1);
            setPage(next);
            void loadTrash(next);
          }}
          disabled={page <= 1 || Boolean(busyId) || loadingList}
        >
          上一页
        </button>
        <span>
          第 {page} / {pageCount} 页（共 {total} 份）
        </span>
        <button
          type="button"
          onClick={() => {
            const next = Math.min(pageCount, page + 1);
            setPage(next);
            void loadTrash(next);
          }}
          disabled={page >= pageCount || Boolean(busyId) || loadingList}
        >
          下一页
        </button>
        <PageJump
          pageCount={pageCount}
          disabled={Boolean(busyId) || loadingList}
          onJump={(target) => {
            setPage(target);
            void loadTrash(target);
          }}
        />
      </div>

      {restoreOpen && (
        <div className="replace-modal-backdrop" role="presentation">
          <section
            className="replace-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="trash-restore-title"
          >
            <div className="results-summary">
              <div>
                <p className="section-number">RESTORE</p>
                <h3 id="trash-restore-title">
                  确认恢复 {selectedCount} 份文档？
                </h3>
              </div>
              <button type="button" onClick={() => setRestoreOpen(false)}>
                关闭
              </button>
            </div>
            <p className="replace-safety-note">
              恢复将重新激活文档、源文件与向量；不会重新解析或重新嵌入。若原件、向量或派生图片已丢失，恢复将失败，请改用彻底删除。
            </p>
            {invalidCategoryDocs.length > 0 && (
              <div className="restore-overrides">
                <p>以下文档的原分类已失效，请为每份选择新的可归档分类：</p>
                {invalidCategoryDocs.map((d) => (
                  <div key={d.doc_id} className="restore-override-row">
                    <span>《{d.title}》</span>
                    <CategoryCascadeSelect
                      categories={categories}
                      value={restoreOverrides[d.doc_id] ?? ''}
                      onChange={(id) =>
                        setRestoreOverrides((prev) => ({ ...prev, [d.doc_id]: id }))
                      }
                      ariaPrefix={`恢复《${d.title}》新`}
                    />
                  </div>
                ))}
              </div>
            )}
            {error && (
              <div className="error-card" role="alert">
                {error}
              </div>
            )}
            <div className="replace-modal-actions">
              <button type="button" onClick={() => setRestoreOpen(false)}>
                取消
              </button>
              <button
                type="button"
                className="primary-button"
                disabled={!restoreReady || Boolean(busyId)}
                onClick={() => void confirmRestore([...selectedDocIds])}
              >
                {busyId === 'batch-restore' || busyId?.startsWith('restore-')
                  ? '正在恢复…'
                  : '确认恢复'}
              </button>
            </div>
          </section>
        </div>
      )}

      {purgeOpen && (
        <div className="replace-modal-backdrop" role="presentation">
          <section
            className="replace-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="trash-purge-title"
          >
            <div className="results-summary">
              <div>
                <p className="section-number">PURGE</p>
                <h3 id="trash-purge-title">
                  确认彻底删除 {selectedCount} 份文档？
                </h3>
              </div>
              <button type="button" onClick={() => setPurgeOpen(false)}>
                关闭
              </button>
            </div>
            <p className="replace-safety-note">
              彻底删除不可恢复：将永久删除文档的原件、向量、图片与来源记录。请谨慎确认。
            </p>
            <ul className="trash-modal-list">
              {selectedItems.map((d) => (
                <li key={d.doc_id}>《{d.title}》（文档 #{d.doc_id}）</li>
              ))}
            </ul>
            <label className="purge-confirm-checkbox">
              <input
                type="checkbox"
                checked={purgeConfirm}
                onChange={(e) => setPurgeConfirm(e.target.checked)}
                aria-label="确认永久删除"
              />
              <span>我确认这些文档及其向量、图片、源文件将被永久删除，且不可恢复。</span>
            </label>
            {error && (
              <div className="error-card" role="alert">
                {error}
              </div>
            )}
            <div className="replace-modal-actions">
              <button type="button" onClick={() => setPurgeOpen(false)}>
                取消
              </button>
              <button
                type="button"
                className="danger-button"
                disabled={!purgeConfirm || Boolean(busyId)}
                onClick={() => void confirmPurge([...selectedDocIds])}
              >
                {busyId === 'batch-purge' || busyId?.startsWith('purge-')
                  ? '正在彻底删除…'
                  : '确认彻底删除'}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
