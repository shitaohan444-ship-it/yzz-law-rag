import { useEffect, useRef, useState } from 'react';
import type { InputHTMLAttributes } from 'react';
import {
  ApiError,
  getKnowledgeDocumentStatus,
  ingestKnowledgeDocument,
  uploadKnowledgeDocument,
} from './api';
import CategoryCascadeSelect from './CategoryCascadeSelect';
import { findCategory } from './knowledgeCategories';
import type { KnowledgeCategoryNode, KnowledgeDocument } from './types';

const MAX_FILES = 500;
const MAX_BYTES = 50 * 1024 * 1024;
const ACCEPT = '.pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff';
const ALLOWED_EXTENSIONS = new Set(ACCEPT.split(','));

// 浏览器目录选择属性（非标准），用断言注入，避免全局类型增强。
const FOLDER_PICKER_ATTRS = {
  webkitdirectory: '',
  directory: '',
} as unknown as InputHTMLAttributes<HTMLInputElement>;

function relativePathOf(file: File): string {
  const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
  return rel || file.name;
}

type FolderStatus =
  | 'waiting'
  | 'uploading'
  | 'registered'
  | 'ingesting'
  | 'success'
  | 'existing'
  | 'failed'
  | 'stopped'
  | 'invalid';

interface FolderItem {
  key: string;
  file: File;
  relativePath: string;
  title: string;
  status: FolderStatus;
  error?: string;
  document?: KnowledgeDocument;
  chunkCount?: number;
  failedPhase?: 'upload' | 'ingest';
  deduplicated?: boolean;
}

interface FolderUploadPanelProps {
  categories: KnowledgeCategoryNode[];
  categoryId: string;
  onCategoryChange: (categoryId: string) => void;
  disabled: boolean;
  onBusyChange: (busy: boolean) => void;
  onDocumentsChanged: () => Promise<void>;
  onCategoryInvalid: () => Promise<void>;
}

const statusLabels: Record<FolderStatus, string> = {
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

function durationLabel(milliseconds: number): string {
  if (milliseconds < 1000) return `${Math.round(milliseconds)} 毫秒`;
  return `${(milliseconds / 1000).toFixed(2)} 秒`;
}

/** 仅纳入允许的文档类型，跳过 Office 临时文件（~$）、隐藏文件（.开头）与无扩展名文件。 */
function isAcceptedDoc(file: File): boolean {
  const name = file.name;
  if (name.startsWith('~$') || name.startsWith('.')) return false;
  const dot = name.lastIndexOf('.');
  if (dot < 0) return false;
  return ALLOWED_EXTENSIONS.has(name.slice(dot).toLowerCase());
}

function sizeError(file: File): string | undefined {
  return file.size > MAX_BYTES ? '文件超过 50MB' : undefined;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '处理失败，请稍后重试';
}

function isConnectivityError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === undefined || error.status === 502 || error.status === 504)
  );
}

export default function FolderUploadPanel({
  categories,
  categoryId,
  onCategoryChange,
  disabled,
  onBusyChange,
  onDocumentsChanged,
  onCategoryInvalid,
}: FolderUploadPanelProps) {
  const [items, setItems] = useState<FolderItem[]>([]);
  const itemsRef = useRef<FolderItem[]>([]);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState('');
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [folderName, setFolderName] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const control = useRef({ paused: false, stopped: false });

  function updateItems(updater: (current: FolderItem[]) => FolderItem[]) {
    setItems((current) => {
      const next = updater(current);
      itemsRef.current = next;
      return next;
    });
  }

  function updateItem(key: string, changes: Partial<FolderItem>) {
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

  async function waitWhilePaused(): Promise<boolean> {
    while (control.current.paused && !control.current.stopped) {
      await new Promise((resolve) => window.setTimeout(resolve, 200));
    }
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
        } else if (isConnectivityError(itemError)) {
          control.current.paused = true;
          setPaused(true);
          setError('平台连接中断，上传队列已暂停；服务恢复后点击“继续”。');
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
    control.current.paused = false;
    await onDocumentsChanged();
  }

  function selectFiles(files: FileList | null) {
    if (!files) return;
    const all = Array.from(files);
    // 仅纳入允许的文档类型，自动跳过临时/隐藏/无关文件
    const accepted = all.filter(isAcceptedDoc);
    if (accepted.length === 0) {
      setError('该文件夹中没有可上传的文档（支持 PDF/Word/TXT/Markdown/图片）');
      updateItems(() => []);
      setFolderName('');
      if (fileInput.current) fileInput.current.value = '';
      return;
    }
    if (accepted.length > MAX_FILES) {
      setError(`一次最多上传 ${MAX_FILES} 个文件，该文件夹内有 ${accepted.length} 个，请拆分或精简后再试`);
      updateItems(() => []);
      setFolderName('');
      if (fileInput.current) fileInput.current.value = '';
      return;
    }
    const next = accepted.map((file, index): FolderItem => {
      const sizeReason = sizeError(file);
      const rel = relativePathOf(file);
      return {
        key: `${rel}-${file.size}-${file.lastModified}-${index}`,
        file,
        relativePath: rel,
        title: file.name.replace(/\.[^.]+$/, ''),
        status: sizeReason ? 'invalid' : 'waiting',
        error: sizeReason,
      };
    });
    itemsRef.current = next;
    setItems(next);
    setError('');
    setStartedAt(null);
    setElapsedMs(0);
    const firstRel = relativePathOf(accepted[0]);
    setFolderName(firstRel.includes('/') ? firstRel.slice(0, firstRel.indexOf('/')) : '已选文件夹');
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
  const count = (status: FolderStatus) => items.filter((item) => item.status === status).length;
  const failedCount = count('failed') + count('invalid');

  return (
    <section className="upload-form batch-upload-panel folder-upload-panel" aria-label="选择本机文件夹上传">
      <div className="batch-upload-heading">
        <div>
          <h3>选择本机文件夹上传（使用真实文件名）</h3>
          <p>在你电脑上选择一个文件夹，浏览器读取里面真实的当前文件并逐个上传入库。</p>
        </div>
        <strong>{items.length} / {MAX_FILES} 个文件</strong>
      </div>
      <label className="batch-file-picker">
        <span>选择本机文件夹</span>
        <input
          ref={fileInput}
          aria-label="选择本机文件夹"
          type="file"
          multiple
          accept={ACCEPT}
          {...FOLDER_PICKER_ATTRS}
          disabled={disabled || running}
          onChange={(event) => selectFiles(event.target.files)}
        />
        <small>
          支持 PDF / Word / TXT / Markdown / 图片；最多 {MAX_FILES} 个，每个不超过 50MB；
          {folderName && ` 已选：${folderName} · 总大小 ${sizeLabel(totalBytes)}`}
        </small>
      </label>
      <CategoryCascadeSelect
        categories={categories}
        value={categoryId}
        onChange={onCategoryChange}
        ariaPrefix="文件夹上传"
        disabled={disabled || running}
        emptyLabel="请选择一级分类"
        className="upload-category-cascade"
      />

      {items.length > 0 && (
        <div className="batch-file-list">
          {items.map((item, index) => (
            <article className="batch-file-row" key={item.key}>
              <div className="batch-file-index">{index + 1}</div>
              <div className="batch-file-main">
                <h4>{item.document?.title ?? item.title}</h4>
                <p>{item.relativePath} · {sizeLabel(item.file.size)}</p>
                {item.document && (
                  <small>
                    文档 #{item.document.doc_id}
                    {item.chunkCount !== undefined ? ` · ${item.chunkCount} 个 Chunk` : ''}
                  </small>
                )}
                {item.error && <small className="batch-file-error">{item.error}</small>}
              </div>
              <div className="batch-file-state">
                <span className={`status-pill status-${item.status}`}>{statusLabels[item.status]}</span>
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
      {error && <div className="error-card" role="alert">{error}</div>}
      <div className="upload-button-group batch-controls">
        <button
          className="primary-button"
          type="button"
          disabled={
            disabled ||
            running ||
            !items.some((item) => item.status === 'waiting') ||
            selectedCategory?.status !== 'active' ||
            !selectedCategory.assignable ||
            selectedCategory.is_system
          }
          onClick={() => void processQueue(false)}
        >
          开始上传
        </button>
        <button type="button" disabled={!running || paused} onClick={pauseQueue}>暂停</button>
        <button type="button" disabled={!running || !paused} onClick={continueQueue}>继续</button>
        <button type="button" disabled={!running} onClick={stopQueue}>停止后续任务</button>
        <button type="button" disabled={disabled || running || count('failed') === 0} onClick={() => void processQueue(true)}>重试失败项</button>
      </div>
    </section>
  );
}
