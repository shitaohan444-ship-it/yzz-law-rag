import { FormEvent, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  appendKnowledgeDocumentSource,
  getKnowledgeDocumentStatus,
  ingestKnowledgeDocument,
  listKnowledgeDocuments,
  listKnowledgeDocumentSources,
  replaceKnowledgeDocumentSource,
  uploadKnowledgeDocument,
} from './api';
import type {
  KnowledgeCategory,
  KnowledgeDocument,
  KnowledgeDocumentStatus,
  KnowledgeDocumentSource,
  ProcessingTimings,
} from './types';

const MAX_BYTES = 50 * 1024 * 1024;
const DOCUMENT_PAGE_SIZE = 5;
const categories: KnowledgeCategory[] = ['法规', '案例', '工作资料'];

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

export default function KnowledgePanel() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<KnowledgeCategory>('法规');
  const [uploading, setUploading] = useState(false);
  const [progressText, setProgressText] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
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
  const [replaceTitle, setReplaceTitle] = useState('');
  const operationStartedAt = useRef<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const replaceFileInput = useRef<HTMLInputElement>(null);

  async function loadDocuments(targetPage = page) {
    setLoadingList(true);
    setError('');
    try {
      let result = await listKnowledgeDocuments({
        page: targetPage,
        pageSize: DOCUMENT_PAGE_SIZE,
        keyword,
        category: categoryFilter,
        status: statusFilter,
      });
      const lastPage = Math.max(1, Math.ceil(result.total / DOCUMENT_PAGE_SIZE));
      if (targetPage > lastPage) {
        result = await listKnowledgeDocuments({
          page: lastPage,
          pageSize: DOCUMENT_PAGE_SIZE,
          keyword,
          category: categoryFilter,
          status: statusFilter,
        });
      }
      setDocuments(result.items);
      setTotal(result.total);
      setPage(result.page);
    } catch (loadError: unknown) {
      setError(messageOf(loadError));
    } finally {
      setLoadingList(false);
    }
  }

  useEffect(() => {
    void loadDocuments(1);
    // 首次进入管理页加载一次；后续筛选由表单提交触发。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const busy = uploading || Boolean(actionId);
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

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !title.trim() || uploading) return;
    if (file.size > MAX_BYTES) {
      setError('文件不能超过 50MB');
      return;
    }
    setUploading(true);
    setError('');
    setNotice('');
    setProgressText('正在上传并登记文档…');
    try {
      const result = await uploadKnowledgeDocument({ file, title, category });
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

  const pageCount = Math.max(1, Math.ceil(total / DOCUMENT_PAGE_SIZE));

  return (
    <section id="knowledge-panel" role="tabpanel" aria-labelledby="knowledge-tab" className="panel">
      <div className="panel-heading">
        <div>
          <p className="section-number">03 / INGEST</p>
          <h2>管理公共知识库</h2>
        </div>
        <p>上传公开法规、公开案例或工作资料。上传成功后会自动解析、切片并写入向量库。</p>
      </div>

      <form className="upload-form" onSubmit={handleUpload}>
        <div className="field-grid">
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
          <label>
            <span>知识分类</span>
            <select aria-label="知识分类" value={category} onChange={(event) => setCategory(event.target.value as KnowledgeCategory)}>
              {categories.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
        </div>
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
            <button className="primary-button" type="submit" disabled={!file || !title.trim() || busy}>
              {uploading ? '正在处理…' : '新建并自动入库'}
            </button>
          </div>
        </div>
      </form>

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
          <span>共 {total} 份</span>
        </div>
        <form
          className="filter-bar"
          onSubmit={(event) => {
            event.preventDefault();
            void loadDocuments(1);
          }}
        >
          <input aria-label="按标题筛选" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="按标题搜索" />
          <select aria-label="按分类筛选" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
            <option value="">全部分类</option>
            {categories.map((item) => <option key={item}>{item}</option>)}
          </select>
          <select aria-label="按状态筛选" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">全部状态</option>
            <option value="pending">等待入库</option>
            <option value="processing">正在入库</option>
            <option value="success">入库成功</option>
            <option value="failed">入库失败</option>
          </select>
          <button className="example-button" type="submit">筛选</button>
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
                    <p>{document.category} · {document.file_name} · {sizeLabel(document.file_size)}</p>
                    <small>
                      文档 #{document.doc_id} · {document.source_count} 个源文件 · {current ? `${current.chunk_count} 个片段 · ${current.image_total} 张图片` : `${document.image_total} 张图片`}
                    </small>
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
        </div>
      </div>

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
    </section>
  );
}
