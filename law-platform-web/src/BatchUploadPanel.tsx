import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ApiError,
  batchMoveKnowledgeDocuments,
  getKnowledgeDocumentStatus,
  ingestKnowledgeDocument,
  uploadKnowledgeDocument,
} from './api';
import CategoryCascadeSelect from './CategoryCascadeSelect';
import {
  countdownLabel,
  durationLabel,
  FAILURE_DELAY_OPTIONS,
  failureDelayLabel,
  loadFailureDelay,
  saveFailureDelay,
} from './batchUploadUtils';
import { findCategory } from './knowledgeCategories';
import { useUploadActivity } from './UploadActivityContext';
import type { KnowledgeCategoryNode, KnowledgeDocument } from './types';

const MAX_FILES = 500;
const MAX_BYTES = 50 * 1024 * 1024;
const ACCEPT = '.pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff';
const ALLOWED_EXTENSIONS = new Set(ACCEPT.split(','));

type BatchStatus =
  | 'waiting'
  | 'uploading'
  | 'registered'
  | 'ingesting'
  | 'success'
  | 'existing'
  | 'failed'
  | 'stopped'
  | 'invalid';

interface BatchItem {
  key: string;
  file: File;
  title: string;
  status: BatchStatus;
  error?: string;
  document?: KnowledgeDocument;
  chunkCount?: number;
  failedPhase?: 'upload' | 'ingest';
  deduplicated?: boolean;
}

interface BatchUploadPanelProps {
  categories: KnowledgeCategoryNode[];
  categoryId: string;
  onCategoryChange: (categoryId: string) => void;
  disabled: boolean;
  onBusyChange: (busy: boolean) => void;
  onDocumentsChanged: () => Promise<void>;
  onCategoryInvalid: () => Promise<void>;
  onEditTitle: (
    document: KnowledgeDocument,
    deduplicated: boolean,
    onUpdated: (document: KnowledgeDocument) => void,
  ) => void;
}

const statusLabels: Record<BatchStatus, string> = {
  waiting: '等待处理',
  uploading: '正在上传',
  registered: '已登记',
  ingesting: '正在解析入库',
  success: '入库成功',
  existing: '文件已存在',
  failed: '处理失败',
  stopped: '已停止',
  invalid: '校验失败',
};

function sizeLabel(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function dateTimeLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未知时间';
  const parts = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(date);
  const valueOf = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? '';
  return `${valueOf('year')}-${valueOf('month')}-${valueOf('day')} ${valueOf('hour')}:${valueOf('minute')}:${valueOf('second')}`;
}

function validationError(file: File): string | undefined {
  if (file.size > MAX_BYTES) return '文件超过 50MB';
  const dot = file.name.lastIndexOf('.');
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
  if (!ALLOWED_EXTENSIONS.has(extension)) return '不支持该文件格式';
  return undefined;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '处理失败，请稍后重试';
}

function isConnectivityError(error: unknown): boolean {
  return error instanceof ApiError &&
    (error.status === undefined || error.status === 502 || error.status === 504);
}

export default function BatchUploadPanel({
  categories,
  categoryId,
  onCategoryChange,
  disabled,
  onBusyChange,
  onDocumentsChanged,
  onCategoryInvalid,
  onEditTitle,
}: BatchUploadPanelProps) {
  const [items, setItems] = useState<BatchItem[]>([]);
  const itemsRef = useRef<BatchItem[]>([]);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState('');
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [failureDelayMs, setFailureDelayMs] = useState(loadFailureDelay);
  const [failureWait, setFailureWait] = useState<{ title: string; remainingMs: number } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const control = useRef({ paused: false, stopped: false });
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveCategoryId, setMoveCategoryId] = useState('');
  const [moveSaving, setMoveSaving] = useState(false);
  const [moveNotice, setMoveNotice] = useState('');
  const { reportActivity } = useUploadActivity();

  // 计算队列状态摘要
  const activeCount = useMemo(
    () => items.filter((i) => i.status === 'uploading' || i.status === 'ingesting' || i.status === 'registered').length,
    [items],
  );
  const doneCount = useMemo(
    () => items.filter((i) => i.status === 'success' || i.status === 'existing').length,
    [items],
  );
  const totalCount = items.filter((i) => i.status !== 'invalid').length;

  // 构建进度文字并上报
  const buildProgressText = useCallback((): string => {
    if (!running) return '';
    if (totalCount > 0 && doneCount > 0 && activeCount >= 0) {
      return `批量导入 ${doneCount}/${totalCount} 份已完成${activeCount > 0 ? `，${activeCount} 份处理中` : ''}`;
    }
    if (activeCount > 0) return `${activeCount} 份文件处理中…`;
    return '';
  }, [running, totalCount, doneCount, activeCount]);

  useEffect(() => {
    if (!running) {
      reportActivity({ busy: false, activeCount: 0, progressText: '' });
      return;
    }
    reportActivity({
      busy: true,
      activeCount,
      progressText: buildProgressText(),
    });
  }, [running, activeCount, buildProgressText, reportActivity]);

  function updateItems(updater: (current: BatchItem[]) => BatchItem[]) {
    setItems((current) => {
      const next = updater(current);
      itemsRef.current = next;
      return next;
    });
  }

  function updateItem(key: string, changes: Partial<BatchItem>) {
    updateItems((current) =>
      current.map((item) => (item.key === key ? { ...item, ...changes } : item)),
    );
  }

  useEffect(() => {
    onBusyChange(running);
    return () => onBusyChange(false);
  }, [onBusyChange, running]);

  useEffect(() => {
    if (!running || startedAt === null) return;
    const update = () => setElapsedMs(Date.now() - startedAt);
    update();
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [running, startedAt]);

  // 自动滚动到当前处理的条目
  useEffect(() => {
    if (activeIndex === null) return;
    const row = document.querySelector<HTMLElement>(
      `.batch-file-list [data-batch-index="${activeIndex}"]`,
    );
    if (row) {
      row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [activeIndex]);

  async function waitWhilePaused(): Promise<boolean> {
    while (control.current.paused && !control.current.stopped) {
      await new Promise((resolve) => window.setTimeout(resolve, 200));
    }
    return !control.current.stopped;
  }

  // 失败后等待 delayMs 再处理下一个；期间实时更新倒计时，并响应“停止/暂停”。
  // 返回 true 表示应继续处理后续任务，false 表示已被停止。
  async function waitAfterFailure(title: string, delayMs: number): Promise<boolean> {
    const deadline = Date.now() + delayMs;
    for (;;) {
      if (control.current.stopped) {
        setFailureWait(null);
        return false;
      }
      if (!control.current.paused) {
        const remainingMs = deadline - Date.now();
        if (remainingMs <= 0) break;
        setFailureWait({ title, remainingMs });
      }
      await new Promise((resolve) => window.setTimeout(resolve, 200));
    }
    setFailureWait(null);
    return !control.current.stopped;
  }

  async function processQueue(retryOnly = false) {
    if (running || disabled) return;
    const selectedCategory = findCategory(categories, categoryId);
    if (!selectedCategory?.assignable || selectedCategory.is_system || selectedCategory.status !== 'active') {
      setError('请选择允许归档的有效知识分类');
      return;
    }
    const processable = itemsRef.current.some((item) =>
      retryOnly ? item.status === 'failed' : item.status === 'waiting',
    );
    if (!processable) return;

    control.current = { paused: false, stopped: false };
    setPaused(false);
    setRunning(true);
    setError('');
    if (!retryOnly || startedAt === null) {
      const now = Date.now();
      setStartedAt(now);
      setElapsedMs(0);
    }

    for (let index = 0; index < itemsRef.current.length; index += 1) {
      let item = itemsRef.current[index];
      const shouldProcess = retryOnly ? item.status === 'failed' : item.status === 'waiting';
      if (!shouldProcess) continue;
      if (!(await waitWhilePaused())) break;
      item = itemsRef.current[index];
      setActiveIndex(index);
      try {
        let document = item.document;
        if (!document || item.failedPhase !== 'ingest') {
          updateItem(item.key, { status: 'uploading', error: undefined, failedPhase: 'upload' });
          const uploaded = await uploadKnowledgeDocument({
            file: item.file,
            title: item.title,
            categoryId,
          });
          document = uploaded.document;
          updateItem(item.key, {
            document,
            status: uploaded.deduplicated ? 'existing' : 'registered',
            deduplicated: uploaded.deduplicated,
            failedPhase: uploaded.deduplicated ? undefined : 'ingest',
          });
          if (uploaded.deduplicated) continue;
        }

        updateItem(item.key, { status: 'ingesting', error: undefined, failedPhase: 'ingest' });
        const ingested = await ingestKnowledgeDocument(document.doc_id, false);
        const status = await getKnowledgeDocumentStatus(document.doc_id);
        if (ingested.status === 'failed' || status.embedding_status === 'failed') {
          throw new ApiError(ingested.message || '文档入库失败');
        }
        updateItem(item.key, {
          status: 'success',
          document,
          chunkCount: status.chunk_count,
          error: undefined,
          failedPhase: undefined,
        });
      } catch (itemError: unknown) {
        updateItem(item.key, { status: 'failed', error: errorMessage(itemError) });
        if (itemError instanceof ApiError && itemError.status === 400 && itemError.message.includes('停用')) {
          control.current.stopped = true;
          setError('所选分类已停用，请重新选择。');
          await onCategoryInvalid();
        } else {
          setError(
            isConnectivityError(itemError)
              ? `平台连接中断，将在${failureDelayLabel(failureDelayMs)}后自动尝试处理下一份文件。`
              : '',
          );
          if (!(await waitAfterFailure(item.title, failureDelayMs))) break;
        }
      }
    }

    if (control.current.stopped) {
      updateItems((current) =>
        current.map((item) =>
          item.status === 'waiting' ? { ...item, status: 'stopped' } : item,
        ),
      );
    }
    setRunning(false);
    setPaused(false);
    setActiveIndex(null);
    control.current.paused = false;
    await onDocumentsChanged();
  }

  function selectFiles(files: FileList | null) {
    if (!files) return;
    const selected = Array.from(files);
    if (selected.length > MAX_FILES) {
      setError(`一次最多选择 ${MAX_FILES} 个文件`);
      updateItems(() => []);
      if (fileInput.current) fileInput.current.value = '';
      return;
    }
    const next = selected.map((file, index): BatchItem => {
      const invalidReason = validationError(file);
      return {
        key: `${file.name}-${file.size}-${file.lastModified}-${index}`,
        file,
        title: file.name,
        status: invalidReason ? 'invalid' : 'waiting',
        error: invalidReason,
      };
    });
    itemsRef.current = next;
    setItems(next);
    setActiveIndex(null);
    setError('');
    setStartedAt(null);
    setElapsedMs(0);
  }

  function pauseQueue() {
    control.current.paused = true;
    setPaused(true);
  }

  function continueQueue() {
    control.current.paused = false;
    setPaused(false);
  }

  function stopQueue() {
    control.current.stopped = true;
    control.current.paused = false;
    setPaused(false);
  }

  const selectedCategory = findCategory(categories, categoryId);
  const totalBytes = items.reduce((sum, item) => sum + item.file.size, 0);
  const count = (status: BatchStatus) => items.filter((item) => item.status === status).length;
  const failedCount = count('failed') + count('invalid');
  const moveCategory = findCategory(categories, moveCategoryId);
  const movableDocIds = items
    .filter((item) => (item.status === 'success' || item.status === 'existing') && item.document)
    .map((item) => item.document!.doc_id);
  const movableCount = movableDocIds.length;

  function openBatchMove() {
    if (movableCount === 0 || running || disabled) return;
    setMoveCategoryId('');
    setError('');
    setMoveNotice('');
    setMoveOpen(true);
  }

  async function submitBatchMove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!moveCategory?.assignable || moveCategory.is_system || moveSaving || movableDocIds.length === 0) return;
    setMoveSaving(true);
    setError('');
    try {
      const target = moveCategory.path.join(' / ');
      const movedCount = movableDocIds.length;
      await batchMoveKnowledgeDocuments({
        docIds: movableDocIds,
        categoryId: moveCategory.id,
      });
      setMoveOpen(false);
      setMoveNotice(`已将 ${movedCount} 份文档移动到“${target}”；未重新解析、生成向量或调用 Qwen。`);
      await onDocumentsChanged();
    } catch (moveError: unknown) {
      setError(errorMessage(moveError));
    } finally {
      setMoveSaving(false);
    }
  }

  return (
    <section className="upload-form batch-upload-panel" aria-label="批量导入知识库文档">
      <div className="batch-upload-heading">
        <div>
          <h3>批量导入独立文档</h3>
          <p>每个文件创建一个独立文档，初始标题为完整文件名。</p>
        </div>
        <strong>{items.length} / {MAX_FILES} 个文件</strong>
      </div>
      <label className="batch-file-picker">
        <span>选择多个文件</span>
        <input
          ref={fileInput}
          aria-label="批量选择文件"
          type="file"
          multiple
          accept={ACCEPT}
          disabled={disabled || running}
          onChange={(event) => selectFiles(event.target.files)}
        />
        <small>最多{MAX_FILES}个文件，每个不超过50MB；已选总大小 {sizeLabel(totalBytes)}</small>
      </label>
      <CategoryCascadeSelect
        categories={categories}
        value={categoryId}
        onChange={onCategoryChange}
        ariaPrefix="批量上传"
        disabled={disabled || running}
        emptyLabel="请选择一级分类"
        className="upload-category-cascade"
      />
      <label className="failure-delay-setting">
        <span>处理失败后等待</span>
        <select
          aria-label="处理失败后等待时间"
          value={failureDelayMs}
          disabled={disabled || running}
          onChange={(event) => {
            const next = saveFailureDelay(Number(event.target.value));
            setFailureDelayMs(next);
          }}
        >
          {FAILURE_DELAY_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <small>等待结束后自动处理下一份文件；默认 2 分钟。</small>
      </label>

      {items.length > 0 && (
        <div className="batch-file-list">
          {items.map((item, index) => (
            <article
              className={`batch-file-row${index === activeIndex ? ' is-processing' : ''}`}
              key={item.key}
              data-batch-index={index}
            >
              <div className="batch-file-index">{index + 1}</div>
              <div className="batch-file-main">
                <h4>{item.document?.title ?? item.title}</h4>
                <p>{item.file.name} · {sizeLabel(item.file.size)}</p>
                {item.document && (
                  <small>
                    文档 #{item.document.doc_id} · 最后上传 {dateTimeLabel(item.document.last_uploaded_at)}
                    {item.chunkCount !== undefined ? ` · ${item.chunkCount} 个 Chunk` : ''}
                  </small>
                )}
                {item.error && <small className="batch-file-error">{item.error}</small>}
              </div>
              <div className="batch-file-state">
                <span className={`status-pill status-${item.status}`}>{statusLabels[item.status]}</span>
                {item.document && (item.status === 'success' || item.status === 'existing') && (
                  <button
                    type="button"
                    disabled={running || disabled}
                    onClick={() =>
                      onEditTitle(item.document!, Boolean(item.deduplicated), (updated) =>
                        updateItem(item.key, { document: updated }),
                      )
                    }
                  >
                    修改标题
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="batch-summary" aria-live="polite">
        <span>成功 {count('success')}</span>
        <span>重复 {count('existing')}</span>
        <span>失败 {failedCount}</span>
        <span>停止 {count('stopped')}</span>
        <span>总耗时 {durationLabel(elapsedMs)}</span>
      </div>
      {failureWait && (
        <div className="loading-card" role="status">
          《{failureWait.title}》处理失败，{countdownLabel(failureWait.remainingMs)} 后自动处理下一个；可点击“暂停”或“停止后续任务”中断等待。
        </div>
      )}
      {error && <div className="error-card" role="alert">{error}</div>}
      <div className="upload-button-group batch-controls">
        <button
          className="primary-button"
          type="button"
          disabled={disabled || running || !items.some((item) => item.status === 'waiting') || selectedCategory?.status !== 'active' || !selectedCategory.assignable || selectedCategory.is_system}
          onClick={() => void processQueue(false)}
        >
          开始批量导入
        </button>
        <button type="button" disabled={!running || paused} onClick={pauseQueue}>暂停</button>
        <button type="button" disabled={!running || !paused} onClick={continueQueue}>继续</button>
        <button type="button" disabled={!running} onClick={stopQueue}>停止后续任务</button>
        <button type="button" disabled={disabled || running || count('failed') === 0} onClick={() => void processQueue(true)}>重试失败项</button>
        <button type="button" disabled={disabled || running || movableCount === 0} onClick={openBatchMove}>移动到其他分类{movableCount > 0 ? `（${movableCount}）` : ''}</button>
      </div>
      {moveNotice && <div className="success-card" role="status">{moveNotice}</div>}
      {moveOpen && (
        <div className="replace-modal-backdrop" role="presentation">
          <section className="replace-modal" role="dialog" aria-modal="true" aria-labelledby="batch-move-title">
            <div className="results-summary">
              <div>
                <p className="section-number">BATCH MOVE</p>
                <h3 id="batch-move-title">批量移动 {movableCount} 份文档到其他分类</h3>
              </div>
              <button type="button" disabled={moveSaving} onClick={() => setMoveOpen(false)}>关闭</button>
            </div>
            <p className="replace-safety-note">只更新数据库分类，不重新解析、不生成向量，也不会调用 Qwen。</p>
            {error && <div className="error-card" role="alert">{error}</div>}
            <form onSubmit={submitBatchMove}>
              <CategoryCascadeSelect
                categories={categories}
                value={moveCategoryId}
                onChange={setMoveCategoryId}
                ariaPrefix="目标"
                emptyLabel="请选择一级分类"
              />
              <div className="replace-modal-actions">
                <button type="button" disabled={moveSaving} onClick={() => setMoveOpen(false)}>取消</button>
                <button className="primary-button" type="submit" disabled={!moveCategory?.assignable || moveCategory.is_system || moveSaving}>{moveSaving ? '正在保存…' : '确认移动分类'}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
