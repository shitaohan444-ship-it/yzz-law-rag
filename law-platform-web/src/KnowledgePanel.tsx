import { FormEvent, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  appendKnowledgeDocumentSource,
  getKnowledgeDocumentStatus,
  ingestKnowledgeDocument,
  listKnowledgeCategories,
  listKnowledgeDocuments,
  listKnowledgeDocumentSources,
  replaceKnowledgeDocumentSource,
  updateKnowledgeDocumentCategory,
  updateKnowledgeDocumentTitle,
  uploadKnowledgeDocument,
} from './api';
import BatchUploadPanel from './BatchUploadPanel';
import CategoryCascadeSelect from './CategoryCascadeSelect';
import PageJump from './PageJump';
import { findCategory, flattenCategories } from './knowledgeCategories';
import { useUploadActivity } from './UploadActivityContext';
import type {
  KnowledgeCategoryNode,
  KnowledgeDocument,
  KnowledgeDocumentStatus,
  KnowledgeDocumentSource,
  ProcessingTimings,
} from './types';

const MAX_BYTES = 50 * 1024 * 1024;
const DEFAULT_DOCUMENT_PAGE_SIZE = 5;
const documentPageSizeOptions = [5, 10, 20, 50, 100, 500, 1000] as const;

const statusLabels: Record<string, string> = {
  pending: '等待入库',
  processing: '正在入库',
  success: '入库成功',
  failed: '入库失败',
  skipped: '已存在',
};

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : '操作失败，请稍后重试';
}

function sizeLabel(value: string | null): string {
  if (!value) return '未知大小';
  const bytes = Number(value);
  if (!Number.isFinite(bytes)) return '未知大小';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function durationLabel(milliseconds: number): string {
  if (milliseconds < 1000) return `${Math.round(milliseconds)} 毫秒`;
  return `${(milliseconds / 1000).toFixed(2)} 秒`;
}

function dateTimeLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未知时间';
  const parts = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')}:${part('second')}`;
}

function previewHref(
  docId: string,
  type: 'markdown' | 'chunks',
  sourceId?: string,
): string {
  const base = `/knowledge/documents/${encodeURIComponent(docId)}/${type}`;
  if (!sourceId) return base;
  const params = new URLSearchParams({ source_id: sourceId });
  if (type === 'chunks') params.set('page', '1');
  return `${base}?${params}`;
}

function TimingGroup({ title, value }: { title: string; value: ProcessingTimings | null }) {
  return (
    <div className="timing-group">
      <h5>{title}</h5>
      {value ? (
        <>
          <p className="timing-total">总耗时 {durationLabel(value.total_ms)}</p>
          <ol>
            {value.stages.map((stage) => (
              <li key={`${stage.key}-${stage.label}`}>
                <span>{stage.label}</span>
                <span>
                  {stage.status === 'skipped' ? '已跳过' : durationLabel(stage.elapsed_ms)}
                  {stage.status === 'failed' ? ' · 失败' : ''}
                </span>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="muted-copy">暂无耗时记录；强制重建后生成。</p>
      )}
    </div>
  );
}

export default function KnowledgePanel({ activeTab }: { activeTab: string }) {
  const [uploadMode, setUploadMode] = useState<'single' | 'batch'>('single');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [categories, setCategories] = useState<KnowledgeCategoryNode[]>([]);
  const [categoryId, setCategoryId] = useState('');
  const [uploading, setUploading] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [progressText, setProgressText] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [documentPageSize, setDocumentPageSize] = useState(DEFAULT_DOCUMENT_PAGE_SIZE);
  const [keyword, setKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loadingList, setLoadingList] = useState(false);
  const [actionId, setActionId] = useState('');
  const [statuses, setStatuses] = useState<Record<string, KnowledgeDocumentStatus>>({});
  const [elapsedMs, setElapsedMs] = useState(0);
  const [appendTarget, setAppendTarget] = useState<KnowledgeDocument | null>(null);
  const [appendFile, setAppendFile] = useState<File | null>(null);
  const [appendTitle, setAppendTitle] = useState('');
  const [manageTarget, setManageTarget] = useState<KnowledgeDocument | null>(null);
  const [sources, setSources] = useState<KnowledgeDocumentSource[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [replaceSource, setReplaceSource] = useState<KnowledgeDocumentSource | null>(null);
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const { reportActivity } = useUploadActivity();
  const [replaceTitle, setReplaceTitle] = useState('');
  const [titleTarget, setTitleTarget] = useState<KnowledgeDocument | null>(null);
  const [titleValue, setTitleValue] = useState('');
  const [titleTargetDeduplicated, setTitleTargetDeduplicated] = useState(false);
  const [titleSaving, setTitleSaving] = useState(false);
  const [moveTarget, setMoveTarget] = useState<KnowledgeDocument | null>(null);
  const [moveCategoryId, setMoveCategoryId] = useState('');
  const titleUpdatedCallback = useRef<((document: KnowledgeDocument) => void) | null>(null);
  const operationStartedAt = useRef<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const replaceFileInput = useRef<HTMLInputElement>(null);

  async function loadCategories(preferredId?: string) {
    const result = await listKnowledgeCategories(true);
    setCategories(result.items);
    const flat = flattenCategories(result.items);
    const isActive = (id: string | undefined) => flat.some((node) => node.id === id && node.status === 'active');
    const selected = preferredId && isActive(preferredId)
      ? preferredId
      : categoryId && isActive(categoryId)
        ? categoryId
        : flat.find((node) => node.status === 'active' && node.assignable && !node.is_system)?.id ?? '';
    setCategoryId(selected);
    if (categoryId && !isActive(categoryId)) {
      setNotice('所选分类已停用，请重新选择。');
    }
    if (categoryFilter && !isActive(categoryFilter)) {
      setCategoryFilter('');
      setNotice('所选分类已停用，请重新选择。');
    }
    return result.items;
  }

  async function loadDocuments(targetPage = page, targetPageSize = documentPageSize) {
    setLoadingList(true);
    setError('');
    try {
      let result = await listKnowledgeDocuments({
        page: targetPage,
        pageSize: targetPageSize,
        keyword,
        categoryId: categoryFilter,
        status: statusFilter,
      });
      const lastPage = Math.max(1, Math.ceil(result.total / targetPageSize));
      if (targetPage > lastPage) {
        result = await listKnowledgeDocuments({
          page: lastPage,
          pageSize: targetPageSize,
          keyword,
          categoryId: categoryFilter,
          status: statusFilter,
        });
      }
      setDocuments(result.items ?? []);
      setTotal(result.total ?? 0);
      setPage(result.page ?? 1);
    } catch (loadError: unknown) {
      setError(messageOf(loadError));
    } finally {
      setLoadingList(false);
    }
  }

  useEffect(() => {
    if (activeTab !== 'knowledge') return;
    void loadDocuments(1);
    void loadCategories().catch((loadError: unknown) => setError(messageOf(loadError)));
    // 首次进入管理页加载一次；后续筛选由表单提交触发。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 标签页切回时自动刷新文档列表（排除首次渲染）
  const prevActiveTabRef = useRef(activeTab);
  useEffect(() => {
    const prev = prevActiveTabRef.current;
    prevActiveTabRef.current = activeTab;
    if (prev !== 'knowledge' && activeTab === 'knowledge') {
      void loadDocuments(page, documentPageSize);
      void loadCategories().catch((loadError: unknown) => setError(messageOf(loadError)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // 上报上传活动到全局 Context
  useEffect(() => {
    const activityBusy = uploading || batchBusy || Boolean(actionId);
    if (!activityBusy) {
      reportActivity({ busy: false, activeCount: 0, progressText: '' });
      return;
    }
    reportActivity({
      busy: true,
      activeCount: batchBusy ? 1 : (uploading || Boolean(actionId) ? 1 : 0),
      progressText,
    });
  }, [uploading, batchBusy, actionId, progressText, reportActivity]);

  const busy = uploading || batchBusy || titleSaving || Boolean(actionId);
  const moveCategory = findCategory(categories, moveCategoryId);
  useEffect(() => {
    if (!busy) {
      operationStartedAt.current = null;
      setElapsedMs(0);
      return;
    }
    if (operationStartedAt.current === null) operationStartedAt.current = performance.now();
    const update = () => {
      if (operationStartedAt.current !== null) {
        setElapsedMs(performance.now() - operationStartedAt.current);
      }
    };
    update();
    const timer = window.setInterval(update, 200);
    return () => window.clearInterval(timer);
  }, [busy]);

  async function runIngest(docId: string, force: boolean) {
    setActionId(docId);
    setProgressText(force ? '正在强制重新入库…' : '正在解析并生成向量…');
    setError('');
    let finished = false;
    let stopPolling: () => void = () => {};
    const pollingStopped = new Promise<void>((resolve) => {
      stopPolling = resolve;
    });
    const polling = (async () => {
      for (let attempt = 0; attempt < 300 && !finished; attempt += 1) {
        await Promise.race([sleep(3000), pollingStopped]);
        if (finished) break;
        try {
          const current = await getKnowledgeDocumentStatus(docId);
          setStatuses((previous) => ({ ...previous, [docId]: current }));
          if (current.embedding_status === 'success' || current.embedding_status === 'failed') {
            break;
          }
        } catch {
          // 入库主请求负责呈现最终错误；短暂轮询失败不覆盖主状态。
        }
      }
    })();
    try {
      const result = await ingestKnowledgeDocument(docId, force);
      finished = true;
      stopPolling();
      await polling;
      const current = await getKnowledgeDocumentStatus(docId);
      setStatuses((previous) => ({ ...previous, [docId]: current }));
      if (result.status === 'failed' || current.embedding_status === 'failed') {
        throw new ApiError(result.message || '文档入库失败');
      }
      setNotice(`《${current.doc_title ?? '未命名文档'}》已入库，共 ${current.chunk_count} 个片段。`);
      await loadDocuments(page);
    } catch (ingestError: unknown) {
      finished = true;
      stopPolling();
      await polling;
      setError(messageOf(ingestError));
    } finally {
      setActionId('');
      setProgressText('');
    }
  }

  function openMove(document: KnowledgeDocument) {
    setMoveTarget(document);
    setMoveCategoryId(document.category_id);
    setError('');
  }

  async function moveDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!moveTarget || !moveCategory?.assignable || moveCategory.is_system || actionId) return;
    setActionId(`move-${moveTarget.doc_id}`);
    setError('');
    setNotice('');
    try {
      const updated = await updateKnowledgeDocumentCategory({
        docId: moveTarget.doc_id,
        categoryId: moveCategory.id,
      });
      setMoveTarget(null);
      setDocuments((current) =>
        current.map((item) => (item.doc_id === updated.doc_id ? updated : item)),
      );
      setNotice(`《${updated.title}》已移动到“${updated.category_path.join(' / ')}”；未重新解析、生成向量或调用 Qwen。`);
    } catch (moveError: unknown) {
      setError(messageOf(moveError));
    } finally {
      setActionId('');
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const uploadCategory = findCategory(categories, categoryId);
    if (!file || !title.trim() || uploading || !uploadCategory?.assignable || uploadCategory.is_system || uploadCategory.status !== 'active') return;
    if (file.size > MAX_BYTES) {
      setError('文件不能超过 50MB');
      return;
    }
    setUploading(true);
    setError('');
    setNotice('');
    setProgressText('正在上传并登记文档…');
    try {
      const result = await uploadKnowledgeDocument({
        file,
        title,
        categoryId,
      });
      setFile(null);
      setTitle('');
      if (fileInput.current) fileInput.current.value = '';
      await loadDocuments(1);
      if (result.deduplicated) {
        setNotice(`该文件已存在，已复用《${result.document.title}》，不会重复向量化。`);
      } else {
        await runIngest(result.document.doc_id, false);
      }
    } catch (uploadError: unknown) {
      setError(messageOf(uploadError));
      if (uploadError instanceof ApiError && uploadError.status === 400 && uploadError.message.includes('停用')) {
        await loadCategories();
      }
    } finally {
      setUploading(false);
      setProgressText('');
    }
  }

  function resetUploadForm() {
    setFile(null);
    setTitle('');
    setNotice('');
    if (fileInput.current) fileInput.current.value = '';
  }

  function openTitleEditor(
    document: KnowledgeDocument,
    deduplicated = false,
    onUpdated?: (document: KnowledgeDocument) => void,
  ) {
    setTitleTarget(document);
    setTitleValue(document.title);
    setTitleTargetDeduplicated(deduplicated);
    titleUpdatedCallback.current = onUpdated ?? null;
    setError('');
  }

  async function handleTitleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!titleTarget || !titleValue.trim() || titleSaving) return;
    setTitleSaving(true);
    setError('');
    try {
      const updated = await updateKnowledgeDocumentTitle({
        docId: titleTarget.doc_id,
        title: titleValue,
      });
      setDocuments((current) => current.map((item) => item.doc_id === updated.doc_id ? updated : item));
      if (manageTarget?.doc_id === updated.doc_id) setManageTarget(updated);
      titleUpdatedCallback.current?.(updated);
      setNotice(`文档 #${updated.doc_id} 标题已修改为《${updated.title}》。`);
      setTitleTarget(null);
      titleUpdatedCallback.current = null;
    } catch (titleError: unknown) {
      setError(messageOf(titleError));
    } finally {
      setTitleSaving(false);
    }
  }

  function openAppend(document: KnowledgeDocument) {
    setAppendTarget(document);
    setAppendFile(null);
    setAppendTitle('');
    setError('');
  }

  async function handleAppend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!appendTarget || !appendFile || !appendTitle.trim() || actionId) return;
    if (appendFile.size > MAX_BYTES) {
      setError('文件不能超过 50MB');
      return;
    }
    setActionId(appendTarget.doc_id);
    setProgressText('正在安全追加后续文件；已有知识库仍可使用…');
    setError('');
    setNotice('');
    try {
      const result = await appendKnowledgeDocumentSource({
        docId: appendTarget.doc_id,
        file: appendFile,
        sourceTitle: appendTitle,
      });
      setNotice(`《${result.document.title}》已追加“${result.source.source_title}”，当前共 ${result.document.source_count} 个源文件、${result.chunk_count} 个 Chunk。`);
      setAppendTarget(null);
      setAppendFile(null);
      await loadDocuments(page);
    } catch (appendError: unknown) {
      setError(messageOf(appendError));
    } finally {
      setActionId('');
      setProgressText('');
    }
  }

  async function openManage(document: KnowledgeDocument) {
    setManageTarget(document);
    setSourcesLoading(true);
    setError('');
    try {
      const result = await listKnowledgeDocumentSources(document.doc_id);
      setSources(result.items);
    } catch (sourceError: unknown) {
      setError(messageOf(sourceError));
    } finally {
      setSourcesLoading(false);
    }
  }

  function openSourceReplacement(source: KnowledgeDocumentSource) {
    setReplaceSource(source);
    setReplaceFile(null);
    setReplaceTitle(source.source_title);
    setError('');
    if (replaceFileInput.current) replaceFileInput.current.value = '';
  }

  async function handleSourceReplace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!manageTarget || !replaceSource || !replaceFile || !replaceTitle.trim() || actionId) return;
    if (replaceFile.size > MAX_BYTES) {
      setError('文件不能超过 50MB');
      return;
    }
    setActionId(manageTarget.doc_id);
    setProgressText('正在安全替换选中的源文件；其他来源仍可使用…');
    setError('');
    setNotice('');
    try {
      const result = await replaceKnowledgeDocumentSource({
        docId: manageTarget.doc_id,
        sourceId: replaceSource.source_id,
        file: replaceFile,
        sourceTitle: replaceTitle,
      });
      setNotice(`源文件“${result.source.source_title}”替换成功，知识库文档编号保持 #${result.document.doc_id}。`);
      setReplaceSource(null);
      setReplaceFile(null);
      const refreshed = await listKnowledgeDocumentSources(manageTarget.doc_id);
      setSources(refreshed.items);
      await loadDocuments(page);
    } catch (replaceError: unknown) {
      setError(messageOf(replaceError));
    } finally {
      setActionId('');
      setProgressText('');
    }
  }

  async function refreshStatus(docId: string) {
    setActionId(docId);
    try {
      const current = await getKnowledgeDocumentStatus(docId);
      setStatuses((previous) => ({ ...previous, [docId]: current }));
    } catch (statusError: unknown) {
      setError(messageOf(statusError));
    } finally {
      setActionId('');
    }
  }

  const pageCount = Math.max(1, Math.ceil(total / documentPageSize));
  const selectedCategory = findCategory(categories, categoryId);
  const selectedFilterCategory = findCategory(categories, categoryFilter);

  return (
    <section id="knowledge-panel" role="tabpanel" aria-labelledby="knowledge-tab" className="panel">
      <div className="panel-heading">
        <div>
          <p className="section-number">03 / INGEST</p>
          <h2>管理公共知识库</h2>
        </div>
        <p>上传公开法规、公开案例或工作资料。上传成功后会自动解析、切片并写入向量库，所有入库资料都会自动供当前局域网使用者检索。</p>
      </div>

      <div className="upload-mode-switch" role="tablist" aria-label="上传方式">
        <button
          type="button"
          role="tab"
          aria-selected={uploadMode === 'single'}
          className={uploadMode === 'single' ? 'is-active' : ''}
          disabled={busy}
          onClick={() => setUploadMode('single')}
        >
          单文件上传
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={uploadMode === 'batch'}
          className={uploadMode === 'batch' ? 'is-active' : ''}
          disabled={busy}
          onClick={() => setUploadMode('batch')}
        >
          批量导入
        </button>
      </div>

      {uploadMode === 'single' ? (
        <form className="upload-form" onSubmit={handleUpload}>
          <div className="field-grid upload-primary-fields">
            <label>
              <span>选择文件</span>
              <input
                ref={fileInput}
                aria-label="选择文件"
                type="file"
                accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
                onChange={(event) => {
                  const next = event.target.files?.[0] ?? null;
                  setFile(next);
                  if (next && !title.trim()) setTitle(next.name.replace(/\.[^.]+$/, ''));
                }}
              />
              <small>单个文件不超过 50MB</small>
            </label>
            <label>
              <span>文档标题</span>
              <input
                aria-label="文档标题"
                type="text"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                maxLength={255}
                placeholder="例如：中华人民共和国劳动合同法"
              />
            </label>
          </div>
          <CategoryCascadeSelect
            categories={categories}
            value={categoryId}
            onChange={setCategoryId}
            ariaPrefix="上传"
            disabled={busy}
            emptyLabel="请选择一级分类"
            className="upload-category-cascade"
          />
          <div className="upload-actions">
            <p>{file ? `${file.name} · ${sizeLabel(String(file.size))}` : '支持 PDF、DOCX、TXT、MD 与常见图片'}</p>
            <div className="upload-button-group">
              {file && (
                <>
                  <button type="button" disabled={busy} onClick={() => fileInput.current?.click()}>
                    重新选择文件
                  </button>
                  <button type="button" disabled={busy} onClick={resetUploadForm}>
                    清除
                  </button>
                </>
              )}
              <button className="primary-button" type="submit" disabled={!file || !title.trim() || selectedCategory?.status !== 'active' || !selectedCategory.assignable || selectedCategory.is_system || busy}>
                {uploading ? '正在处理…' : '新建并自动入库'}
              </button>
            </div>
          </div>
        </form>
      ) : (
        <BatchUploadPanel
          categories={categories}
          categoryId={categoryId}
          onCategoryChange={setCategoryId}
          disabled={uploading || Boolean(actionId) || titleSaving}
          onBusyChange={setBatchBusy}
          onDocumentsChanged={() => loadDocuments(1)}
          onCategoryInvalid={async () => { await loadCategories(); }}
          onEditTitle={openTitleEditor}
        />
      )}

      <div className="response-region" aria-live="polite" aria-busy={uploading || Boolean(actionId)}>
        {progressText && (
          <div className="loading-card">
            {progressText} 已等待 {durationLabel(elapsedMs)}
          </div>
        )}
        {notice && <div className="success-card" role="status">{notice}</div>}
        {error && <div className="error-card" role="alert">{error}</div>}
      </div>

      <div className="document-section">
        <div className="results-summary">
          <h3>已登记文档</h3>
          <div className="list-summary-controls">
            <span>共 {total} 份</span>
            <label>
              <span>每页显示</span>
              <select
                aria-label="已登记文档每页数量"
                value={documentPageSize}
                disabled={loadingList}
                onChange={(event) => {
                  const nextPageSize = Number(event.target.value);
                  setDocumentPageSize(nextPageSize);
                  void loadDocuments(1, nextPageSize);
                }}
              >
                {documentPageSizeOptions.map((value) => (
                  <option key={value} value={value}>{value} 份</option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <form
          className="filter-bar knowledge-filter-bar"
          onSubmit={(event) => {
            event.preventDefault();
            void (async () => {
              try {
                const latestCategories = await loadCategories();
                const latestFilter = categoryFilter
                  ? findCategory(latestCategories, categoryFilter)
                  : undefined;
                if (categoryFilter && latestFilter?.status !== 'active') return;
                await loadDocuments(1);
              } catch (filterError: unknown) {
                setError(messageOf(filterError));
              }
            })();
          }}
        >
          <input aria-label="按标题筛选" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="按标题搜索" />
          <CategoryCascadeSelect
            categories={categories}
            value={categoryFilter}
            onChange={setCategoryFilter}
            ariaPrefix="筛选"
            includeSystem
            allowEmpty
            emptyLabel="全部分类"
            className="filter-category-cascade"
            showPath={false}
          />
          <select aria-label="按状态筛选" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">全部状态</option>
            <option value="pending">等待入库</option>
            <option value="processing">正在入库</option>
            <option value="success">入库成功</option>
            <option value="failed">入库失败</option>
          </select>
          <button className="example-button" type="submit">筛选</button>
          {selectedFilterCategory && (
            <small className="category-filter-path">
              当前路径：{selectedFilterCategory.path.join(' / ')}
              {!selectedFilterCategory.assignable && ' · 请选择可直接归档的下级分类'}
            </small>
          )}
        </form>

        {loadingList && <div className="loading-card">正在加载文档列表…</div>}
        {!loadingList && documents.length === 0 && <div className="empty-card">还没有符合条件的公共知识库文档。</div>}
        {!loadingList && documents.length > 0 && (
          <div className="document-list">
            {documents.map((document) => {
              const current = statuses[document.doc_id];
              const status = current?.embedding_status ?? document.embedding_status;
              const uploadTimings = current?.upload_timings ?? document.upload_timings;
              const ingestTimings = current?.ingest_timings ?? document.ingest_timings;
              return (
                <article className="document-card" key={document.doc_id}>
                  <div className="document-main">
                    <div className="document-title-row">
                      <h4>{document.title}</h4>
                      <span className={`status-pill status-${status}`}>{statusLabels[status] ?? status}</span>
                    </div>
                    <p>{document.category_path?.join(' / ') || document.category} · {document.file_name} · {sizeLabel(document.file_size)}</p>
                    <small>
                      文档 #{document.doc_id} · {document.source_count} 个源文件 · {current ? `${current.chunk_count} 个片段 · ${current.image_total} 张图片` : `${document.image_total} 张图片`}
                    </small>
                    <small className="upload-time">最后上传：{dateTimeLabel(document.last_uploaded_at)}</small>
                    <details className="timing-details">
                      <summary>处理耗时</summary>
                      <div className="timing-grid">
                        <TimingGroup title="上传登记" value={uploadTimings} />
                        <TimingGroup title="RAG 入库" value={ingestTimings} />
                      </div>
                    </details>
                  </div>
                  <div className="document-actions">
                    <button type="button" onClick={() => void refreshStatus(document.doc_id)} disabled={Boolean(actionId)}>刷新状态</button>
                    <button type="button" onClick={() => openTitleEditor(document)} disabled={busy}>修改标题</button>
                    <button type="button" onClick={() => openMove(document)} disabled={busy}>移动到其他分类</button>
                    {status === 'success' ? (
                      <>
                        <a className="document-action-link" href={previewHref(document.doc_id, 'markdown')} target="_blank" rel="noopener noreferrer">查看 Markdown</a>
                        <a className="document-action-link" href={previewHref(document.doc_id, 'chunks')} target="_blank" rel="noopener noreferrer">查看 Chunk</a>
                      </>
                    ) : (
                      <>
                        <span className="document-action-link is-disabled" aria-disabled="true">查看 Markdown</span>
                        <span className="document-action-link is-disabled" aria-disabled="true">查看 Chunk</span>
                      </>
                    )}
                    <button type="button" onClick={() => openAppend(document)} disabled={busy || status !== 'success'}>追加文件</button>
                    <button type="button" onClick={() => void openManage(document)} disabled={busy || status !== 'success'}>管理文件</button>
                    {status === 'failed' && <button type="button" onClick={() => void runIngest(document.doc_id, false)} disabled={Boolean(actionId)}>重试入库</button>}
                    {status === 'success' && <button type="button" onClick={() => void runIngest(document.doc_id, true)} disabled={Boolean(actionId)}>强制重建</button>}
                  </div>
                </article>
              );
            })}
          </div>
        )}
        <div className="pagination">
          <button type="button" disabled={page <= 1 || loadingList} onClick={() => void loadDocuments(page - 1)}>上一页</button>
          <span>第 {page} / {pageCount} 页</span>
          <button type="button" disabled={page >= pageCount || loadingList} onClick={() => void loadDocuments(page + 1)}>下一页</button>
          <PageJump pageCount={pageCount} disabled={loadingList} onJump={(target) => void loadDocuments(target)} />
        </div>
      </div>

      {titleTarget && (
        <div className="replace-modal-backdrop" role="presentation">
          <section className="replace-modal" role="dialog" aria-modal="true" aria-labelledby="document-title-edit-heading">
            <div className="results-summary">
              <div>
                <p className="section-number">EDIT TITLE</p>
                <h3 id="document-title-edit-heading">修改文档标题</h3>
              </div>
              <button type="button" disabled={titleSaving} onClick={() => setTitleTarget(null)}>关闭</button>
            </div>
            {titleTargetDeduplicated && (
              <p className="replace-safety-note">该文件已存在，修改标题将影响现有知识库文档。</p>
            )}
            <p className="muted-copy">只修改页面和检索引用中的标题，不会重新解析文件或生成向量，最后上传时间保持不变。</p>
            {error && <div className="error-card" role="alert">{error}</div>}
            <form onSubmit={handleTitleUpdate}>
              <label>
                <span>文档标题</span>
                <input
                  autoFocus
                  aria-label="修改后的文档标题"
                  value={titleValue}
                  maxLength={255}
                  disabled={titleSaving}
                  onChange={(event) => setTitleValue(event.target.value)}
                />
              </label>
              <div className="replace-modal-actions">
                <button type="button" disabled={titleSaving} onClick={() => setTitleTarget(null)}>取消</button>
                <button className="primary-button" type="submit" disabled={!titleValue.trim() || titleSaving}>
                  {titleSaving ? '正在保存…' : '确认修改标题'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {appendTarget && (
        <div className="replace-modal-backdrop" role="presentation">
          <section className="replace-modal" role="dialog" aria-modal="true" aria-labelledby="append-title">
            <div className="results-summary">
              <div>
                <p className="section-number">APPEND SOURCE</p>
                <h3 id="append-title">向现有知识库追加文件</h3>
              </div>
              <button type="button" disabled={Boolean(actionId)} onClick={() => setAppendTarget(null)}>关闭</button>
            </div>
            <p className="replace-safety-note">
              新文件入库成功后才加入《{appendTarget.title}》；处理失败不会影响已有文件和 Chunk。
            </p>
            {actionId === appendTarget.doc_id && progressText && (
              <div className="loading-card">{progressText} 已等待 {durationLabel(elapsedMs)}</div>
            )}
            {error && <div className="error-card" role="alert">{error}</div>}
            <form onSubmit={handleAppend}>
              <label>
                <span>后续文件</span>
                <input
                  aria-label="后续文件"
                  type="file"
                  accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
                  disabled={Boolean(actionId)}
                  onChange={(event) => {
                    const next = event.target.files?.[0] ?? null;
                    setAppendFile(next);
                    if (next) setAppendTitle(next.name);
                  }}
                />
                <small>{appendFile ? `${appendFile.name} · ${sizeLabel(String(appendFile.size))}` : '每次追加一个文件，单个文件不超过 50MB'}</small>
              </label>
              <label>
                <span>来源标题</span>
                <input aria-label="来源标题" value={appendTitle} maxLength={255} disabled={Boolean(actionId)} onChange={(event) => setAppendTitle(event.target.value)} />
              </label>
              <div className="replace-modal-actions">
                <button type="button" disabled={Boolean(actionId)} onClick={() => setAppendTarget(null)}>取消</button>
                <button className="primary-button" type="submit" disabled={!appendFile || !appendTitle.trim() || Boolean(actionId)}>
                  {actionId ? '正在安全追加…' : '确认追加文件'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {manageTarget && (
        <div className="replace-modal-backdrop" role="presentation">
          <section className="replace-modal source-manager" role="dialog" aria-modal="true" aria-labelledby="manage-title">
            <div className="results-summary">
              <div>
                <p className="section-number">SOURCE FILES</p>
                <h3 id="manage-title">管理《{manageTarget.title}》的源文件</h3>
              </div>
              <button type="button" disabled={Boolean(actionId)} onClick={() => setManageTarget(null)}>关闭</button>
            </div>
            {sourcesLoading && <div className="loading-card">正在加载源文件…</div>}
            <div className="source-file-list">
              {sources.map((source) => (
                <article className="source-file-card" key={source.source_id}>
                  <div>
                    <h4>{source.source_title} {source.is_primary && <span className="status-pill">主文件</span>}</h4>
                    <p>{source.file_name} · {sizeLabel(source.file_size)}</p>
                    <small>来源 #{source.source_id} · {source.chunk_count} 个 Chunk · {source.image_total} 张图片</small>
                    <small className="upload-time">上传时间：{dateTimeLabel(source.uploaded_at)}</small>
                    <details className="timing-details">
                      <summary>处理耗时</summary>
                      <div className="timing-grid">
                        <TimingGroup title="上传登记" value={source.upload_timings} />
                        <TimingGroup title="RAG 入库" value={source.ingest_timings} />
                      </div>
                    </details>
                  </div>
                  <div className="document-actions">
                    <a className="document-action-link" href={previewHref(manageTarget.doc_id, 'markdown', source.source_id)} target="_blank" rel="noopener noreferrer">查看 Markdown</a>
                    <a className="document-action-link" href={previewHref(manageTarget.doc_id, 'chunks', source.source_id)} target="_blank" rel="noopener noreferrer">查看 Chunk</a>
                    <button type="button" disabled={Boolean(actionId)} onClick={() => openSourceReplacement(source)}>替换文件</button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}

      {replaceSource && manageTarget && (
        <div className="replace-modal-backdrop nested-modal" role="presentation">
          <section className="replace-modal" role="dialog" aria-modal="true" aria-labelledby="source-replace-title">
            <div className="results-summary">
              <div>
                <p className="section-number">SAFE SOURCE REPLACE</p>
                <h3 id="source-replace-title">替换源文件</h3>
              </div>
              <button type="button" disabled={Boolean(actionId)} onClick={() => setReplaceSource(null)}>关闭</button>
            </div>
            <p className="replace-safety-note">只替换“{replaceSource.source_title}”；其他源文件和 Chunk 保持不变。</p>
            {progressText && <div className="loading-card">{progressText} 已等待 {durationLabel(elapsedMs)}</div>}
            {error && <div className="error-card" role="alert">{error}</div>}
            <form onSubmit={handleSourceReplace}>
              <label>
                <span>新的源文件</span>
                <input ref={replaceFileInput} aria-label="新的源文件" type="file" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff" disabled={Boolean(actionId)} onChange={(event) => setReplaceFile(event.target.files?.[0] ?? null)} />
              </label>
              <label>
                <span>来源标题</span>
                <input aria-label="替换来源标题" value={replaceTitle} maxLength={255} disabled={Boolean(actionId)} onChange={(event) => setReplaceTitle(event.target.value)} />
              </label>
              <div className="replace-modal-actions">
                <button type="button" disabled={Boolean(actionId)} onClick={() => setReplaceSource(null)}>取消</button>
                <button className="primary-button" type="submit" disabled={!replaceFile || !replaceTitle.trim() || Boolean(actionId)}>{actionId ? '正在安全替换…' : '确认替换源文件'}</button>
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
              <button type="button" disabled={Boolean(actionId)} onClick={() => setMoveTarget(null)}>关闭</button>
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
                <button type="button" disabled={Boolean(actionId)} onClick={() => setMoveTarget(null)}>取消</button>
                <button className="primary-button" type="submit" disabled={!moveCategory?.assignable || moveCategory.is_system || Boolean(actionId)}>{actionId ? '正在保存…' : '确认移动分类'}</button>
              </div>
            </form>
          </section>
        </div>
      )}

    </section>
  );
}
