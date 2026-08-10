import { DragEvent, FormEvent, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  cancelDraftingLiteJob,
  confirmDraftingLiteParties,
  createDraftingLiteJob,
  downloadDraftingLiteArtifact,
  downloadDraftingLiteDocument,
  getDraftingLiteJob,
  listDraftingLiteCauses,
  listDraftingLiteMaterials,
  selectDraftingLiteCause,
} from './api';
import type {
  DraftingLiteCause,
  DraftingLiteJob,
  DraftingLiteMaterial,
  DraftingLiteMaterialList,
  DraftingLiteStatus,
  PartyRecord,
} from './types';

const JOB_ID_STORAGE_KEY = 'drafting-lite-job-id';

function savedJobId(): string | null {
  try {
    return sessionStorage.getItem(JOB_ID_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistJobId(jobId: string | null): void {
  try {
    if (jobId) {
      sessionStorage.setItem(JOB_ID_STORAGE_KEY, jobId);
    } else {
      sessionStorage.removeItem(JOB_ID_STORAGE_KEY);
    }
  } catch {
    // 无痕模式等环境静默忽略
  }
}

const statusLabels: Record<DraftingLiteStatus, string> = {
  queued: '等待处理',
  parsing: '材料与案情解析 Agent',
  matching_cause: '正在识别案由',
  waiting_cause_selection: '需要选择案由',
  waiting_party_confirmation: '需要确认当事人',
  retrieving_laws: '法律检索 Agent',
  drafting: '起诉状撰写 Agent',
  rendering: '正在回填模板',
  drafting_evidence: '正在整理证据目录',
  rendering_evidence: '正在生成证据目录',
  collecting_evidence_media: '正在收集证据原件',
  packaging_evidence: '正在生成证据材料包',
  completed: '生成完成',
  cancelled: '已取消',
  failed: '生成失败',
};

const activeStatuses = new Set<DraftingLiteStatus>([
  'queued',
  'parsing',
  'matching_cause',
  'retrieving_laws',
  'drafting',
  'rendering',
  'drafting_evidence',
  'rendering_evidence',
  'collecting_evidence_media',
  'packaging_evidence',
]);

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : '操作失败，请稍后重试';
}

function acceptFiles(items: File[]): File[] {
  return items.filter((file) => /\.(pdf|docx?|jpe?g|png)$/i.test(file.name));
}

function newParty(index: number): PartyRecord {
  return {
    party_id: `user-${Date.now()}-${index}`,
    role: 'plaintiff',
    entity_type: 'natural_person',
    field_provenance: {},
    field_conflicts: {},
  };
}

function sourceLabel(source: PartyRecord['field_provenance'][string][number]): string {
  if (source.source_type === 'user') return '用户确认';
  if (source.source_type === 'computed') return source.note || '系统默认';
  return `${source.file_name || '材料'}${source.page_no ? `第${source.page_no}页` : '（页码缺失）'}`;
}

export default function LegalDraftingPanel({ active = true }: { active?: boolean }) {
  const [files, setFiles] = useState<File[]>([]);
  const [cause, setCause] = useState('auto');
  const [causes, setCauses] = useState<DraftingLiteCause[]>([]);
  const [fallbackCause, setFallbackCause] = useState('');
  const [job, setJob] = useState<DraftingLiteJob | null>(null);
  const [partyDraft, setPartyDraft] = useState<PartyRecord[]>([]);
  const [knowledgeMaterials, setKnowledgeMaterials] = useState<DraftingLiteMaterial[]>([]);
  const [materialPicker, setMaterialPicker] = useState(false);
  const [materialResults, setMaterialResults] = useState<DraftingLiteMaterialList>({
    items: [], total: 0, page: 1, page_size: 10,
  });
  const [materialKeyword, setMaterialKeyword] = useState('');
  const [materialCaseStatus, setMaterialCaseStatus] = useState<'all' | 'open' | 'closed'>('all');
  const [materialBusy, setMaterialBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const downloadedJob = useRef<string | null>(null);
  const cancelledJobs = useRef(new Set<string>());
  // 标记初始化是否完成，防止恢复中重复触发自动下载
  const initialized = useRef(false);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    listDraftingLiteCauses()
      .then((result) => {
        if (cancelled) return;
        const items = Array.isArray(result.items) ? result.items : [];
        setCauses(items);
        setFallbackCause((current) => (
          items.some((item) => item.code === current)
            ? current
            : items[0]?.code ?? ''
        ));
      })
      .catch((reason) => {
        if (!cancelled) setError(message(reason));
      });
    return () => { cancelled = true; };
  }, [active]);

  useEffect(() => {
    if (!job || !activeStatuses.has(job.status)) return;
    const timer = window.setInterval(() => {
      getDraftingLiteJob(job.job_id)
        .then((latest) => {
          if (!cancelledJobs.current.has(job.job_id)) setJob(latest);
        })
        .catch((reason) => setError(message(reason)));
    }, 1800);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    if (job?.status !== 'waiting_party_confirmation') return;
    setPartyDraft(job.party_extraction?.parties ?? []);
  }, [job?.job_id, job?.party_input_version, job?.status]);

  useEffect(() => {
    if (job?.status !== 'waiting_cause_selection' || !job.cause_candidates.length) return;
    setFallbackCause(job.cause_candidates[0].cause_code);
  }, [job?.job_id, job?.status, job?.cause_candidates]);

  // 组件挂载时从 sessionStorage 恢复 jobId，向后端查询真实任务状态
  useEffect(() => {
    if (!active || initialized.current) return;
    initialized.current = true;
    const storedId = savedJobId();
    if (!storedId) return;
    let cancelled = false;
    getDraftingLiteJob(storedId)
      .then((existing) => {
        if (cancelled) return;
        if (!existing || existing.status === 'failed' || existing.status === 'cancelled') {
          // 失败或已清理的任务不恢复
          persistJobId(null);
          return;
        }
        setJob(existing);
      })
      .catch(() => {
        if (cancelled) return;
        // 后端查询失败（任务过期/不存在），清除存储
        persistJobId(null);
      });
    return () => { cancelled = true; };
  }, [active]);

  useEffect(() => {
    if (!materialPicker) return;
    void loadMaterials(1);
  }, [materialPicker, materialCaseStatus]);

  async function loadMaterials(page = 1) {
    setMaterialBusy(true);
    setError('');
    try {
      setMaterialResults(await listDraftingLiteMaterials({
        keyword: materialKeyword,
        page,
        pageSize: 10,
        caseStatus: materialCaseStatus,
      }));
    } catch (reason) {
      setError(message(reason));
    } finally {
      setMaterialBusy(false);
    }
  }

  useEffect(() => {
    if (job?.status !== 'completed' || downloadedJob.current === job.job_id) return;
    downloadedJob.current = job.job_id;
    void download(job.job_id, true);
  }, [job?.job_id, job?.status]);

  function addFiles(incoming: File[]) {
    setError('');
    const accepted = acceptFiles(incoming);
    if (accepted.length !== incoming.length) {
      setError('仅支持 PDF、DOC、DOCX、JPG 和 PNG 文件');
    }
    setFiles((current) => {
      const remaining = Math.max(0, 10 - knowledgeMaterials.length - current.length);
      if (accepted.length > remaining) {
        setError('知识库材料和临时上传合计最多10份');
      }
      return [...current, ...accepted.slice(0, remaining)];
    });
  }

  function toggleKnowledgeMaterial(material: DraftingLiteMaterial) {
    setError('');
    setKnowledgeMaterials((current) => {
      const selected = current.some((item) => item.document_id === material.document_id);
      if (selected) {
        return current.filter((item) => item.document_id !== material.document_id);
      }
      if (current.length + files.length >= 10) {
        setError('知识库材料和临时上传合计最多10份');
        return current;
      }
      return [...current, material];
    });
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    addFiles(Array.from(event.dataTransfer.files));
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if ((!files.length && !knowledgeMaterials.length) || busy) return;
    setBusy(true);
    setError('');
    downloadedJob.current = null;
    try {
      const created = await createDraftingLiteJob(
        files,
        cause,
        knowledgeMaterials.map((item) => item.document_id),
      );
      setJob(created);
      // 持久化 jobId 到 sessionStorage，支持 tab 切换和浏览器刷新恢复
      persistJobId(created.job_id);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function continueWithCause() {
    if (!job || !fallbackCause || busy) return;
    setBusy(true);
    setError('');
    try {
      setJob(await selectDraftingLiteCause(job.job_id, fallbackCause));
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function cancelDrafting() {
    if (!job || busy) return;
    if (!window.confirm('确定取消本次起诉状撰写吗？已生成的中间结果不会作为文书保留。')) return;
    cancelledJobs.current.add(job.job_id);
    setBusy(true);
    setError('');
    try {
      const cancelled = await cancelDraftingLiteJob(job.job_id);
      setJob(cancelled);
      persistJobId(null);
      downloadedJob.current = null;
    } catch (reason) {
      cancelledJobs.current.delete(job.job_id);
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  function updateParty(index: number, patch: Partial<PartyRecord>) {
    setPartyDraft((current) => current.map((party, item) => (
      item === index ? { ...party, ...patch } : party
    )));
  }

  async function continueWithParties() {
    if (!job || busy) return;
    setBusy(true);
    setError('');
    try {
      setJob(await confirmDraftingLiteParties({
        jobId: job.job_id,
        version: job.party_input_version,
        parties: partyDraft,
      }));
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function download(
    jobId: string,
    automatic = false,
    artifactType: 'complaint' | 'evidence_directory' | 'evidence_package' = 'complaint',
  ) {
    setError('');
    try {
      const result = artifactType === 'complaint'
        ? await downloadDraftingLiteDocument(jobId)
        : await downloadDraftingLiteArtifact(jobId, artifactType);
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = result.filename;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (reason) {
      if (automatic) downloadedJob.current = null;
      setError(message(reason));
    }
  }

  function reset() {
    setJob(null);
    setFiles([]);
    setKnowledgeMaterials([]);
    setCause('auto');
    setPartyDraft([]);
    setError('');
    downloadedJob.current = null;
    persistJobId(null);
  }

  return (
    <section id="drafting-panel" role="tabpanel" aria-labelledby="drafting-tab" className="panel drafting-panel">
      <div className="panel-heading">
        <div>
          <p className="section-number">03 / MATERIAL-DRIVEN AGENTS</p>
          <h2>当事人材料生成要素式起诉状</h2>
        </div>
        <p>选择已入库卷宗或补充上传材料，自动识别案由、匹配法条并生成 DOCX。</p>
      </div>

      {!job && (
        <form className="drafting-lite-form" onSubmit={create}>
          <div className="drafting-source-actions">
            <div>
              <strong>知识库当事人案件材料</strong>
              <p>直接读取已入库 Markdown 和 chunks，不重复执行 OCR 或 VL。</p>
            </div>
            <button
              className="primary-button"
              type="button"
              onClick={() => setMaterialPicker(true)}
            >
              从知识库选择
            </button>
          </div>

          {knowledgeMaterials.length > 0 && (
            <ul className="drafting-file-list">
              {knowledgeMaterials.map((material) => (
                <li key={material.document_id}>
                  <span>
                    <strong><em className="material-kind">知识库</em>{material.title}</strong>
                    <small>{material.category_path.join(' / ')} · {material.source_count} 个来源</small>
                  </span>
                  <button type="button" onClick={() => toggleKnowledgeMaterial(material)}>移除</button>
                </li>
              ))}
            </ul>
          )}

          <div
            className="drafting-dropzone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <strong>本地补充上传</strong>
            <p>支持 PDF、DOC、DOCX、JPG、PNG；两类材料合计最多10份，总大小不超过100MB。</p>
            <label className="primary-button drafting-file-button">
              选择文件
              <input
                aria-label="选择当事人材料"
                type="file"
                accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                multiple
                onChange={(event) => addFiles(Array.from(event.target.files ?? []))}
              />
            </label>
          </div>

          {files.length > 0 && (
            <ul className="drafting-file-list">
              {files.map((file, index) => (
                <li key={`${file.name}-${file.lastModified}-${index}`}>
                  <span><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(2)} MB</small></span>
                  <button type="button" onClick={() => setFiles((current) => current.filter((_, item) => item !== index))}>移除</button>
                </li>
              ))}
            </ul>
          )}

          <label className="drafting-cause-select">
            案由选择
            <select value={cause} onChange={(event) => setCause(event.target.value)}>
              <option value="auto">根据当事人材料自动选择</option>
              {causes.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
            </select>
            <small>默认由材料与案情解析 Agent 判断；手工选择将直接覆盖自动结果。</small>
          </label>

          <button
            className="primary-button drafting-generate-button"
            disabled={(!files.length && !knowledgeMaterials.length) || busy}
          >
            {busy ? '正在创建任务…' : '分析材料并生成起诉状'}
          </button>
        </form>
      )}

      {materialPicker && (
        <div className="drafting-modal-backdrop" role="presentation">
          <section
            className="drafting-material-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="material-picker-title"
          >
            <div className="drafting-modal-heading">
              <div>
                <small>KNOWLEDGE MATERIALS</small>
                <h3 id="material-picker-title">选择当事人案件材料</h3>
              </div>
              <button type="button" aria-label="关闭材料选择" onClick={() => setMaterialPicker(false)}>×</button>
            </div>
            <form
              className="drafting-material-search"
              onSubmit={(event) => {
                event.preventDefault();
                void loadMaterials(1);
              }}
            >
              <input
                aria-label="搜索知识库材料"
                value={materialKeyword}
                placeholder="输入卷宗标题"
                onChange={(event) => setMaterialKeyword(event.target.value)}
              />
              <select
                aria-label="案件状态"
                value={materialCaseStatus}
                onChange={(event) => setMaterialCaseStatus(event.target.value as 'all' | 'open' | 'closed')}
              >
                <option value="all">全部</option>
                <option value="open">未结案</option>
                <option value="closed">已结案</option>
              </select>
              <button className="example-button" type="submit">搜索</button>
            </form>
            <div className="drafting-material-results">
              {materialBusy && <p>正在读取材料目录…</p>}
              {!materialBusy && materialResults.items.length === 0 && <p>没有找到可选的成功入库材料。</p>}
              {!materialBusy && materialResults.items.map((material) => {
                const checked = knowledgeMaterials.some((item) => item.document_id === material.document_id);
                return (
                  <label key={material.document_id} className={checked ? 'is-selected' : ''}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleKnowledgeMaterial(material)}
                    />
                    <span>
                      <strong>{material.title}</strong>
                      <small>
                        {material.category_path.join(' / ')} · {material.file_name}
                      </small>
                      <small>
                        {material.source_count} 个来源 · {material.image_total} 张图片 ·
                        更新于 {new Date(material.last_uploaded_at).toLocaleString('zh-CN')}
                      </small>
                    </span>
                  </label>
                );
              })}
            </div>
            <div className="drafting-modal-footer">
              <span>已选 {knowledgeMaterials.length} 份，合计 {knowledgeMaterials.length + files.length}/10</span>
              <div>
                <button
                  className="example-button"
                  type="button"
                  disabled={materialResults.page <= 1 || materialBusy}
                  onClick={() => void loadMaterials(materialResults.page - 1)}
                >
                  上一页
                </button>
                <span>{materialResults.page} / {Math.max(1, Math.ceil(materialResults.total / materialResults.page_size))}</span>
                <button
                  className="example-button"
                  type="button"
                  disabled={materialResults.page * materialResults.page_size >= materialResults.total || materialBusy}
                  onClick={() => void loadMaterials(materialResults.page + 1)}
                >
                  下一页
                </button>
                <button className="primary-button" type="button" onClick={() => setMaterialPicker(false)}>完成选择</button>
              </div>
            </div>
          </section>
        </div>
      )}

      {error && <div className="error-card" role="alert">{error}</div>}

      {job && (
        <div className="drafting-workspace">
          <div className="drafting-status">
            <div>
              <small>任务 {job.job_id.slice(0, 8)}</small>
              <h3>{job.template_name || '正在根据材料选择模板'}</h3>
            </div>
            <span className={`status-pill status-${job.status}`}>{statusLabels[job.status]}</span>
          </div>

          {!['completed', 'failed', 'cancelled'].includes(job.status) && (
            <div className="drafting-cancel-row">
              <button
                className="example-button danger-button"
                type="button"
                disabled={busy}
                onClick={() => void cancelDrafting()}
              >
                {busy ? '正在处理…' : '取消本次撰写'}
              </button>
            </div>
          )}

          <div className="drafting-progress" aria-label={`生成进度 ${job.progress}%`}>
            <div style={{ width: `${job.progress}%` }} />
            <span>
              {job.progress}% · {
                job.status === 'parsing' && job.input_mode === 'knowledge'
                  ? '读取知识库 Markdown'
                  : job.status === 'parsing' && job.input_mode === 'mixed'
                    ? '读取知识库 Markdown并解析临时材料'
                    : statusLabels[job.status]
              }
            </span>
          </div>

          {!!job.selected_materials?.length && (
            <div className="drafting-review">
              <h3>本次当事人材料</h3>
              {job.selected_materials.map((item, index) => (
                <p key={`${item.source_kind}-${item.document_id || item.title}-${index}`}>
                  <strong>{item.source_kind === 'knowledge' ? '知识库材料' : '临时上传'} · {item.title}</strong>
                </p>
              ))}
            </div>
          )}

          {job.cause_label && (
            <div className="drafting-cause-result">
              <div><small>识别案由</small><strong>{job.cause_label}</strong></div>
              <div><small>匹配置信度</small><strong>{job.confidence === null ? '—' : `${(job.confidence * 100).toFixed(0)}%`}</strong></div>
            </div>
          )}

          {job.cause_evidence.length > 0 && (
            <div className="drafting-review">
              <h3>案由判断依据</h3>
              {job.cause_evidence.map((item, index) => (
                <p key={`${item.file_name}-${item.page_no}-${index}`}>
                  <strong>{item.file_name || '上传材料'}{item.page_no ? ` · 第${item.page_no}页` : ''}</strong>
                  {item.chunk_id ? ` · chunk ${item.chunk_id}` : ''}
                  {item.reason ? `：${item.reason}` : ''}
                </p>
              ))}
            </div>
          )}

          {job.status === 'waiting_cause_selection' && (
            <div className="drafting-inputs">
              <h3>材料不足以可靠判断案由</h3>
              <p>以下是最符合材料的三个案由及匹配度，请人工确认。该选择只决定模板，不会被当作材料事实。</p>
              {job.cause_candidates.length > 0 && (
                <div className="drafting-cause-candidates" role="radiogroup" aria-label="候选案由">
                  {job.cause_candidates.slice(0, 3).map((candidate) => (
                    <label
                      key={candidate.cause_code}
                      className={fallbackCause === candidate.cause_code ? 'is-selected' : ''}
                    >
                      <input
                        type="radio"
                        name="drafting-cause-candidate"
                        value={candidate.cause_code}
                        checked={fallbackCause === candidate.cause_code}
                        onChange={(event) => setFallbackCause(event.target.value)}
                      />
                      <span>
                        <strong>{candidate.label}</strong>
                        <small>{(candidate.confidence * 100).toFixed(0)}%</small>
                      </span>
                    </label>
                  ))}
                </div>
              )}
              <label>
                选择其他案由
                <select value={fallbackCause} onChange={(event) => setFallbackCause(event.target.value)}>
                  {causes.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
                </select>
              </label>
              <button className="primary-button" type="button" disabled={busy || !fallbackCause} onClick={continueWithCause}>
                {busy ? '正在继续…' : '按所选案由继续生成'}
              </button>
            </div>
          )}

          {job.status === 'waiting_party_confirmation' && (
            <div className="drafting-inputs drafting-party-confirmation">
              <h3>确认当事人信息</h3>
              <p>关键字段缺失、冲突或模板无法表达多人结构时，任务会停在这里。修改后确认即可继续，不会重复解析材料。</p>

              {job.party_issues.length > 0 && (
                <div className="warning-card" role="status">
                  <strong>需要处理的问题</strong>
                  <ul>
                    {job.party_issues.map((issue, index) => (
                      <li key={`${issue.code}-${issue.party_id || ''}-${issue.field || ''}-${index}`}>
                        {issue.message}
                        {!!issue.candidates?.length && (
                          <span className="drafting-conflict-candidates">
                            候选值：{issue.candidates.map((candidate) => (
                              `${String(candidate.value)}（${
                                candidate.sources?.map(sourceLabel).join('；') || '来源待核验'
                              }）`
                            )).join('；')}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {partyDraft.map((party, index) => (
                <section className="drafting-party-card" key={party.party_id}>
                  <div className="drafting-party-heading">
                    <strong>当事人 {index + 1}</strong>
                    <button
                      className="example-button"
                      type="button"
                      onClick={() => setPartyDraft((current) => current.filter((_, item) => item !== index))}
                    >
                      删除
                    </button>
                  </div>
                  <div className="drafting-party-grid">
                    <label>
                      诉讼角色
                      <select
                        value={party.role}
                        onChange={(event) => updateParty(index, {
                          role: event.target.value as PartyRecord['role'],
                        })}
                      >
                        <option value="plaintiff">原告</option>
                        <option value="defendant">被告</option>
                        <option value="third_party">第三人</option>
                        <option value="unknown">待确认</option>
                      </select>
                    </label>
                    <label>
                      主体类型
                      <select
                        value={party.entity_type}
                        onChange={(event) => updateParty(index, {
                          entity_type: event.target.value as PartyRecord['entity_type'],
                        })}
                      >
                        <option value="natural_person">自然人</option>
                        <option value="organization">法人或其他组织</option>
                        <option value="unknown">待确认</option>
                      </select>
                    </label>

                    {party.entity_type !== 'organization' ? (
                      <>
                        {([
                          ['name', '姓名'],
                          ['gender', '性别'],
                          ['birth_date', '出生日期'],
                          ['ethnicity', '民族'],
                          ['id_number', '证件号码'],
                          ['phone', '联系电话'],
                          ['address', '户籍地址'],
                          ['current_address', '现住址'],
                        ] as const).map(([field, label]) => (
                          <label key={field}>
                            {label}
                            <input
                              value={party[field] ?? ''}
                              onChange={(event) => updateParty(index, { [field]: event.target.value })}
                            />
                            {!!party.field_provenance[field]?.length && (
                              <small>来源：{party.field_provenance[field].map(sourceLabel).join('；')}</small>
                            )}
                          </label>
                        ))}
                      </>
                    ) : (
                      <>
                        {([
                          ['organization_name', '组织名称'],
                          ['unified_social_credit_code', '统一社会信用代码'],
                          ['organization_address', '住所地'],
                          ['organization_registration_address', '登记地址'],
                          ['organization_phone', '联系电话'],
                          ['legal_representative', '法定代表人'],
                        ] as const).map(([field, label]) => (
                          <label key={field}>
                            {label}
                            <input
                              value={party[field] ?? ''}
                              onChange={(event) => updateParty(index, { [field]: event.target.value })}
                            />
                            {!!party.field_provenance[field]?.length && (
                              <small>来源：{party.field_provenance[field].map(sourceLabel).join('；')}</small>
                            )}
                          </label>
                        ))}
                      </>
                    )}
                  </div>
                </section>
              ))}

              <div className="drafting-party-actions">
                <button
                  className="example-button"
                  type="button"
                  onClick={() => setPartyDraft((current) => [...current, newParty(current.length)])}
                >
                  增加当事人
                </button>
                <button className="primary-button" type="button" disabled={busy} onClick={continueWithParties}>
                  {busy ? '正在校验…' : '确认当事人并继续生成'}
                </button>
              </div>
            </div>
          )}

          {job.warnings.length > 0 && (
            <div className="warning-card" role="status">
              <strong>生成提示</strong>
              <ul>{job.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul>
            </div>
          )}

          {job.status === 'completed' && (
            <div className="success-card drafting-complete">
              <div>
                <strong>要素式起诉状、证据目录及证据材料包已生成</strong>
                <p>浏览器已自动下载起诉状；证据目录和证据材料包请通过独立按钮下载。</p>
                {job.evidence_package_status === 'partial' && (
                  <p className="drafting-package-warning">部分证据材料未能取得原件，压缩包内已附缺失说明。</p>
                )}
              </div>
              <div className="drafting-download-actions">
                <button className="primary-button" type="button" onClick={() => download(job.job_id)}>下载起诉状</button>
                {job.artifacts?.some((item) => item.type === 'evidence_directory') && (
                  <button className="example-button" type="button" onClick={() => download(job.job_id, false, 'evidence_directory')}>下载证据目录</button>
                )}
                {job.artifacts?.some((item) => item.type === 'evidence_package') && (
                  <button className="example-button" type="button" onClick={() => download(job.job_id, false, 'evidence_package')}>下载证据材料包（ZIP）</button>
                )}
              </div>
            </div>
          )}

          {job.status === 'failed' && (
            <div className="error-card" role="alert">
              <strong>生成失败</strong>
              <p>{job.error_message || '未返回具体错误，请稍后重试。'}</p>
            </div>
          )}

          {job.status === 'cancelled' && (
            <div className="warning-card" role="status">
              <strong>本次撰写已取消</strong>
              <p>任务已停止，不会再继续检索、撰写或生成 DOCX。</p>
            </div>
          )}

          {(job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') && (
            <button className="example-button" type="button" onClick={reset}>新建文书任务</button>
          )}
        </div>
      )}
    </section>
  );
}
