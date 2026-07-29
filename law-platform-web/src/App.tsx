import { FormEvent, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ApiError, chatRag, searchRag } from './api';
import AppNavigation from './AppNavigation';
import { createSessionId } from './session';
import KnowledgePanel from './KnowledgePanel';
import LegalDraftingPanel from './LegalDraftingPanel';
import type { ChatResponse, RagHit, SearchResponse } from './types';

type ActiveTab = 'search' | 'chat' | 'drafting' | 'knowledge';

const searchExample = '试用期工资最低不能少于多少';
const chatExample = '产品缺陷造成损害生产厂家要赔吗';

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '发生未知错误，请稍后重试';
}

function scoreLabel(score: number): string {
  const normalized = score <= 1 ? score * 100 : score;
  return `${Math.max(0, Math.min(100, normalized)).toFixed(1)}%`;
}

function HitMeta({ hit }: { hit: RagHit }) {
  return (
    <div className="result-meta">
      {hit.article_no && <span className="tag accent">{hit.article_no}</span>}
      {hit.chapter && <span className="tag">{hit.chapter}</span>}
      {hit.page_no && <span className="tag">第 {hit.page_no} 页</span>}
      <span className="score">相关度 {scoreLabel(hit.score)}</span>
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>(() => {
    const requested = new URLSearchParams(window.location.search).get('tab');
    return requested === 'knowledge' || requested === 'chat' || requested === 'drafting' ? requested : 'search';
  });
  const [sessionId] = useState(createSessionId);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchTopK, setSearchTopK] = useState(5);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [searchError, setSearchError] = useState('');
  const [searching, setSearching] = useState(false);
  const [question, setQuestion] = useState('');
  const [chatTopK, setChatTopK] = useState(5);
  const [chatResult, setChatResult] = useState<ChatResponse | null>(null);
  const [chatError, setChatError] = useState('');
  const [chatting, setChatting] = useState(false);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!searchQuery.trim() || searching) return;
    setSearching(true);
    setSearchError('');
    setSearchResult(null);
    try {
      setSearchResult(await searchRag(searchQuery, searchTopK));
    } catch (error: unknown) {
      setSearchError(errorMessage(error));
    } finally {
      setSearching(false);
    }
  }

  async function handleChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim() || chatting) return;
    setChatting(true);
    setChatError('');
    setChatResult(null);
    try {
      setChatResult(await chatRag(question, chatTopK, sessionId));
    } catch (error: unknown) {
      setChatError(errorMessage(error));
    } finally {
      setChatting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">LAW RAG · 局域网验收版</p>
          <h1>法律知识检索台</h1>
          <p className="hero-copy">
            从已入库的法律法规中检索原文，并通过有出处的回答快速核对法律依据。
          </p>
        </div>
        <div className="gateway-status" aria-label="连接方式：平台网关">
          <span aria-hidden="true" />
          经平台网关访问
        </div>
      </header>

      <main className="workspace">
        <AppNavigation active={activeTab} onSelect={setActiveTab} />

        {activeTab === 'search' ? (
          <section
            id="search-panel"
            role="tabpanel"
            aria-labelledby="search-tab"
            className="panel"
          >
            <div className="panel-heading">
              <div>
                <p className="section-number">01 / RETRIEVE</p>
                <h2>检索法律依据</h2>
              </div>
              <p>输入自然语言问题，系统将返回经过精排的知识库片段。</p>
            </div>
            <form onSubmit={handleSearch} className="query-form">
              <label htmlFor="search-query">检索问题</label>
              <textarea
                id="search-query"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="例如：试用期工资最低不能少于多少？"
                maxLength={2000}
                rows={4}
              />
              <div className="form-footer">
                <button
                  className="example-button"
                  type="button"
                  onClick={() => setSearchQuery(searchExample)}
                >
                  填入验收问题
                </button>
                <label className="top-k-control" htmlFor="search-top-k">
                  返回数量
                  <select
                    id="search-top-k"
                    value={searchTopK}
                    onChange={(event) => setSearchTopK(Number(event.target.value))}
                  >
                    {[3, 5, 8, 10].map((value) => (
                      <option key={value} value={value}>
                        {value} 条
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={!searchQuery.trim() || searching}
                >
                  {searching ? '正在检索…' : '开始检索'}
                </button>
              </div>
            </form>

            <div className="response-region" aria-live="polite" aria-busy={searching}>
              {searching && <div className="loading-card">正在召回并精排相关法条…</div>}
              {searchError && <div className="error-card" role="alert">{searchError}</div>}
              {searchResult && searchResult.hits.length === 0 && (
                <div className="empty-card">没有找到相关知识库片段，请换一种问法。</div>
              )}
              {searchResult && searchResult.hits.length > 0 && (
                <div className="results">
                  <div className="results-summary">
                    <h3>检索结果</h3>
                    <span>共 {searchResult.total} 条</span>
                  </div>
                  {searchResult.hits.map((hit, index) => (
                    <article className="result-card" key={hit.chunk_id}>
                      <div className="result-index">{String(index + 1).padStart(2, '0')}</div>
                      <div className="result-content">
                        <div className="result-title-row">
                          <h4>{hit.doc_title || '未命名文档'}</h4>
                          <span className="source">{hit.source}</span>
                        </div>
                        <HitMeta hit={hit} />
                        <p className="excerpt">{hit.text}</p>
                        <details>
                          <summary>展开完整片段</summary>
                          <div className="full-text">{hit.text}</div>
                        </details>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </section>
        ) : activeTab === 'chat' ? (
          <section
            id="chat-panel"
            role="tabpanel"
            aria-labelledby="chat-tab"
            className="panel"
          >
            <div className="panel-heading">
              <div>
                <p className="section-number">02 / ANSWER</p>
                <h2>询问知识库</h2>
              </div>
              <p>回答必须附带知识库引用；没有依据时，请以拒答提示为准。</p>
            </div>
            <form onSubmit={handleChat} className="query-form">
              <label htmlFor="chat-question">法律问题</label>
              <textarea
                id="chat-question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="例如：产品缺陷造成损害，生产厂家是否要承担责任？"
                maxLength={4000}
                rows={4}
              />
              <div className="form-footer">
                <button
                  className="example-button"
                  type="button"
                  onClick={() => setQuestion(chatExample)}
                >
                  填入验收问题
                </button>
                <label className="top-k-control" htmlFor="chat-top-k">
                  引用数量
                  <select
                    id="chat-top-k"
                    value={chatTopK}
                    onChange={(event) => setChatTopK(Number(event.target.value))}
                  >
                    {[3, 5, 8, 10].map((value) => (
                      <option key={value} value={value}>
                        {value} 条
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={!question.trim() || chatting}
                >
                  {chatting ? '正在生成…' : '提交问题'}
                </button>
              </div>
            </form>

            <div className="response-region" aria-live="polite" aria-busy={chatting}>
              {chatting && <div className="loading-card">正在检索依据并生成回答…</div>}
              {chatError && <div className="error-card" role="alert">{chatError}</div>}
              {chatResult && (
                <div className="answer-layout">
                  <article className="answer-card">
                    <div className="answer-heading">
                      <div>
                        <p className="section-number">RAG ANSWER</p>
                        <h3>知识库回答</h3>
                      </div>
                      <span>{chatResult.hits_count} 条依据</span>
                    </div>
                    {chatResult.refs.length === 0 && (
                      <div className="insufficient-notice" role="status">
                        <strong>知识库依据不足</strong>
                        当前回答没有可引用的知识库片段，请勿将其作为法律结论。
                      </div>
                    )}
                    <div className="markdown-answer">
                      <ReactMarkdown
                        components={{
                          a: (props) => (
                            <a {...props} target="_blank" rel="noreferrer noopener" />
                          ),
                        }}
                      >
                        {chatResult.answer}
                      </ReactMarkdown>
                    </div>
                  </article>

                  {chatResult.refs.length > 0 && (
                    <aside className="references" aria-label="引用依据">
                      <div className="results-summary">
                        <h3>引用依据</h3>
                        <span>{chatResult.refs.length} 条</span>
                      </div>
                      {chatResult.refs.map((ref) => (
                        <details className="reference-card" key={`${ref.ref_id}-${ref.chunk_id}`}>
                          <summary>
                            <span className="ref-number">[{ref.ref_id}]</span>
                            <span>
                              <strong>{ref.doc_title || '未命名文档'}</strong>
                              <small>{ref.article_no || ref.chapter || ref.source}</small>
                            </span>
                          </summary>
                          <HitMeta hit={ref} />
                          <div className="full-text">{ref.text}</div>
                        </details>
                      ))}
                    </aside>
                  )}
                </div>
              )}
            </div>
          </section>
        ) : activeTab === 'drafting' ? (
          <LegalDraftingPanel active />
        ) : (
          <KnowledgePanel />
        )}
      </main>

      <footer>
        <span>回答仅用于知识检索与测试，不替代律师正式法律意见。</span>
        <span>当前会话仅在本页面有效</span>
      </footer>
    </div>
  );
}
