import { useEffect, useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  ApiError,
  getKnowledgeDocumentChunks,
  getKnowledgeDocumentMarkdown,
  listKnowledgeDocumentSources,
} from './api';
import PageJump from './PageJump';
import type {
  KnowledgeDocumentChunk,
  KnowledgeDocumentChunks,
  KnowledgeDocumentMarkdown,
  KnowledgeDocumentSource,
} from './types';

const CHUNK_PAGE_SIZE = 20;

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return '文档或来源不存在';
    if (error.status === 502) return 'Chunk 服务暂时不可用，请稍后重试';
    return error.message;
  }
  return '预览加载失败，请稍后重试';
}

function validDocId(value: string | undefined): value is string {
  return Boolean(value && /^[1-9]\d*$/.test(value));
}

function sourceIdOf(params: URLSearchParams): string | undefined {
  const value = params.get('source_id');
  return value && /^[1-9]\d*$/.test(value) ? value : undefined;
}

function pageOf(params: URLSearchParams): number {
  const value = Number(params.get('page') ?? '1');
  return Number.isInteger(value) && value > 0 ? value : 1;
}

function SourceSelector({
  label,
  sources,
  value,
  onChange,
}: {
  label: string;
  sources: KnowledgeDocumentSource[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="preview-source-control">
      <span>{label}</span>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">全部源文件</option>
        {sources.map((source) => (
          <option key={source.source_id} value={source.source_id}>
            {source.source_title}{source.is_primary ? '（主文件）' : ''}
          </option>
        ))}
      </select>
    </label>
  );
}

function PreviewShell({
  eyebrow,
  title,
  summary,
  children,
}: {
  eyebrow: string;
  title: string;
  summary: string;
  children: ReactNode;
}) {
  return (
    <div className="preview-shell">
      <header className="preview-header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p>{summary}</p>
        </div>
        <div className="preview-navigation">
          <a href="/?tab=knowledge">返回知识库管理</a>
          <button type="button" onClick={() => window.close()}>关闭本页</button>
        </div>
      </header>
      <main className="preview-workspace">{children}</main>
    </div>
  );
}

export function MarkdownPreviewPage() {
  const { docId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const sourceId = sourceIdOf(searchParams);
  const [sources, setSources] = useState<KnowledgeDocumentSource[]>([]);
  const [document, setDocument] = useState<KnowledgeDocumentMarkdown | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!validDocId(docId)) {
      setError('文档编号无效');
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    Promise.all([
      listKnowledgeDocumentSources(docId),
      getKnowledgeDocumentMarkdown(docId, sourceId),
    ])
      .then(([sourceResult, markdown]) => {
        if (cancelled) return;
        setSources(sourceResult.items);
        setDocument(markdown);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(messageOf(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [docId, sourceId]);

  function selectSource(value: string) {
    setSearchParams(value ? { source_id: value } : {});
  }

  return (
    <PreviewShell
      eyebrow="KNOWLEDGE · MARKDOWN"
      title={document?.doc_title || 'Markdown 预览'}
      summary={document ? `文档 #${document.doc_id} · ${document.source_count} 个来源 · ${document.image_count} 张图片` : '正在读取知识库 Markdown'}
    >
      <section className="preview-panel" aria-label="文档 Markdown 预览">
        <div className="preview-toolbar">
          <div>
            <h2>Markdown 正文</h2>
            <p>{sourceId ? '当前仅显示选中的源文件' : '当前合并显示全部有效源文件'}</p>
          </div>
          <SourceSelector label="Markdown 来源筛选" sources={sources} value={sourceId ?? ''} onChange={selectSource} />
        </div>
        {loading && <div className="loading-card">正在加载 Markdown…</div>}
        {error && <div className="error-card" role="alert">{error}</div>}
        {!loading && !error && document && !document.markdown.trim() && (
          <div className="empty-card">该来源暂无可预览的 Markdown。</div>
        )}
        {!loading && !error && document?.markdown.trim() && (
          <article className="markdown-document">
            <ReactMarkdown
              skipHtml
              components={{
                img: () => <span className="image-placeholder">[文档图片已解析，预览中不直接访问 MinIO]</span>,
              }}
            >
              {document.markdown}
            </ReactMarkdown>
          </article>
        )}
      </section>
    </PreviewShell>
  );
}

function ChunkTags({ chunk }: { chunk: KnowledgeDocumentChunk }) {
  const tags = [
    chunk.source,
    chunk.source_title ? `来源：${chunk.source_title}` : null,
    chunk.source_file_name,
    chunk.source_chunk_idx !== null ? `来源内序号 ${chunk.source_chunk_idx}` : null,
    chunk.article_no ? `法条 ${chunk.article_no}` : null,
    chunk.chapter ? `章节 ${chunk.chapter}` : null,
    chunk.page_no ? `第 ${chunk.page_no} 页` : null,
    chunk.content_type,
    chunk.image_category ? `图片 ${chunk.image_category}` : null,
  ].filter(Boolean);
  return tags.length ? (
    <div className="chunk-tags">{tags.map((tag) => <span key={String(tag)}>{tag}</span>)}</div>
  ) : null;
}

export function ChunkPreviewPage() {
  const { docId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const sourceId = sourceIdOf(searchParams);
  const requestedPage = pageOf(searchParams);
  const [sources, setSources] = useState<KnowledgeDocumentSource[]>([]);
  const [chunks, setChunks] = useState<KnowledgeDocumentChunks | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!validDocId(docId)) {
      setError('文档编号无效');
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    Promise.all([
      listKnowledgeDocumentSources(docId),
      getKnowledgeDocumentChunks(docId, requestedPage, CHUNK_PAGE_SIZE, sourceId),
    ])
      .then(([sourceResult, chunkResult]) => {
        if (cancelled) return;
        setSources(sourceResult.items);
        setChunks(chunkResult);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(messageOf(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [docId, requestedPage, sourceId]);

  function updateLocation(nextSourceId: string | undefined, nextPage: number) {
    const next = new URLSearchParams();
    if (nextSourceId) next.set('source_id', nextSourceId);
    next.set('page', String(nextPage));
    setSearchParams(next);
  }

  const pageCount = chunks ? Math.max(1, Math.ceil(chunks.total / chunks.page_size)) : 1;
  return (
    <PreviewShell
      eyebrow="KNOWLEDGE · CHUNKS"
      title={chunks?.doc_title || 'Chunk 预览'}
      summary={chunks ? `文档 #${chunks.doc_id} · 共 ${chunks.total} 个 Chunk` : '正在读取向量库切片'}
    >
      <section className="preview-panel" aria-label="文档 Chunk 预览">
        <div className="preview-toolbar">
          <div>
            <h2>Chunk 明细</h2>
            <p>{sourceId ? '当前仅显示选中的源文件' : '当前显示全部有效源文件'}</p>
          </div>
          <SourceSelector
            label="Chunk 来源筛选"
            sources={sources}
            value={sourceId ?? ''}
            onChange={(value) => updateLocation(value || undefined, 1)}
          />
        </div>
        {loading && <div className="loading-card">正在加载 Chunk…</div>}
        {error && <div className="error-card" role="alert">{error}</div>}
        {!loading && !error && chunks?.items.length === 0 && (
          <div className="empty-card">该范围内没有 Chunk。</div>
        )}
        {!loading && !error && chunks && chunks.items.length > 0 && (
          <div className="chunk-list">
            {chunks.items.map((chunk) => (
              <article className="chunk-card" key={chunk.chunk_id}>
                <div className="chunk-heading">
                  <strong>{chunk.chunk_id}</strong>
                  <span>全局序号 {chunk.chunk_idx} · {chunk.char_count} 字符</span>
                </div>
                <ChunkTags chunk={chunk} />
                <pre>{chunk.text}</pre>
              </article>
            ))}
          </div>
        )}
        {!loading && !error && chunks && (
          <div className="pagination">
            <button type="button" disabled={requestedPage <= 1} onClick={() => updateLocation(sourceId, requestedPage - 1)}>上一页</button>
            <span>第 {requestedPage} / {pageCount} 页</span>
            <button type="button" disabled={requestedPage >= pageCount} onClick={() => updateLocation(sourceId, requestedPage + 1)}>下一页</button>
            <PageJump pageCount={pageCount} disabled={loading} onJump={(target) => updateLocation(sourceId, target)} />
          </div>
        )}
      </section>
    </PreviewShell>
  );
}
