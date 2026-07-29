"""配置：pydantic-settings 读 .env。

变量名沿用 law-rag-kb/.env.example 命名（与 Node 侧 law-platform-api 一致，跨后端统一），
不复用 law-rag-service 的旧命名（MINIO_HOST/ROOT_USER）。
"""
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 固定到 law-rag-kb/（config.py 位于 app/core/，向上 3 级），不再依赖进程 cwd。
# 历史 gotcha：env_file=".env" 是相对 cwd，从项目根跑 tests/脚本会读不到 .env、
# 用默认值（如 llm_enable_thinking=None），导致 test_llm 等失败。
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # 服务
    kb_api_port: int = 8000
    app_env: str = "development"  # development / test / production

    # 服务间认证与 Web 暴露面。生产环境必须启用认证并配置至少 32 字符随机 Token。
    auth_enabled: bool = False
    rag_service_token: str = ""
    auth_admin_role_codes: str = "rag_admin,system_admin,super_admin"
    cors_allowed_origins: str = ""  # 逗号分隔；空值表示不启用浏览器跨域
    trusted_hosts: str = "localhost,127.0.0.1,testserver,rag-api,law-rag-kb"
    expose_api_docs: bool = True  # production 会被强制关闭
    max_request_body_bytes: int = 110_100_480

    # PostgreSQL（只读 oa schema）
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "law_rag"
    postgres_user: str = "law_rag_user"
    postgres_password: str = "law_rag_password"
    pg_schema: str = "oa"

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # MinIO（读 law-firm-files 文档原件）
    minio_endpoint: str = "localhost"
    minio_port: int = 9000
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "law-firm-files"
    minio_use_ssl: bool = False
    minio_presigned_expires_seconds: int = 300  # 最小暴露窗口；生产默认 5 分钟

    # Embedding / Reranker（本地推理）
    # 注意：Settings 用 extra="ignore"，未在此声明的 .env 变量会被静默丢弃
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    model_device: str = "cpu"  # cpu / cuda / mps

    # 阶段 2 入库链
    milvus_collection: str = "kb_chunks"
    chunk_size: int = 500  # 字符数（中文友好）；token 精确切分留阶段 6
    chunk_overlap: int = 64
    embedding_batch_size: int = 16  # CPU 起步值，防内存吃紧
    embedding_max_seq_len: int = 8192  # BGE-M3 最大上下文
    chunk_by_article: bool = True  # 阶段6：条款级切片（识别"第X条"边界+metadata）；False=纯字符递归

    # 图片理解（清洗后、切片前）
    vl_enabled: bool = True
    vl_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    vl_api_key: str = ""
    vl_model: str = "qwen3-vl-plus"
    vl_timeout_seconds: float = 60.0
    vl_max_retries: int = 3
    vl_concurrency: int = 4
    vl_prompt_version: str = "v1"
    vl_filter_confidence: float = 0.9
    # 表格/流程图的中文描述 JSON 可能较长；1000 易在 finish_reason=length 截断导致 JSONDecodeError。
    # .env 若显式设置同名变量则以其为准。
    vl_max_output_tokens: int = 2048
    vl_nearby_text_chars: int = 800
    scan_page_min_text_chars: int = 40
    pdf_render_scale: float = 1.5

    # 阶段 3 检索链
    search_top_k: int = 8  # hybrid 召回数（dense + sparse 融合后取 N，喂给 reranker）
    rerank_top_k: int = 5  # reranker 精排后返回给调用方的片段数
    rrf_k: int = 60  # RRF 融合常数；阶段 6 若改 weighted 配比则不用
    hnsw_ef: int = 64  # dense HNSW 检索 ef（≥ search_top_k，越大召回越全、越慢）
    rerank_batch_size: int = 2  # CPU 按长度排序后小批推理，减少长短候选混合 padding
    rerank_min_score: float = 0.3  # 阶段6：rerank 分数 < 此值的片段丢弃（保底留 top-1 防空）；0=不过滤
    hybrid_ranker: str = "rrf"  # 阶段6：hybrid 融合策略 rrf / weighted
    dense_weight: float = 0.5  # hybrid_ranker=weighted 时 dense 向量权重
    sparse_weight: float = 0.5  # hybrid_ranker=weighted 时 sparse 向量权重
    search_timing_enabled: bool = False  # 输出 /search 各阶段耗时；排障后可关闭

    # 阶段 4 生成链
    llm_provider: str = "stub"  # stub（链路验证，模板答案）/ openai（OpenAI 兼容，DeepSeek/智谱/通义）/ ollama
    llm_api_base: str = ""  # provider=openai 时的 base_url（如 https://api.deepseek.com/v1）
    llm_api_key: str = ""
    llm_model: str = ""  # 模型名（如 deepseek-chat / glm-4-flash / qwen2.5:7b）
    llm_timeout_seconds: float = 90.0
    llm_max_retries: int = 2
    llm_max_tokens: int = 1200
    llm_temperature: float = 0.2
    # None=不发送厂商扩展参数；Qwen3.x 建议显式 false，降低 RAG 延迟与推理 token 成本
    llm_enable_thinking: bool | None = None
    chat_top_k: int = 5  # /chat 送给 LLM 的检索片段数（默认同 rerank_top_k）
    chat_max_context_chars: int = 4000  # prompt 里片段总字符上限，防爆 token

    # 文档 Markdown 渲染（GET /documents/{id}/markdown）
    kb_generate_description: bool = True  # 入库时是否生成文档级中文摘要
    kb_description_max_chars: int = 4000  # 生成摘要时喂给 LLM 的正文截断上限
    # 统一切片流水线：doc→Markdown→切片（chunk_text 带 #img:{id} 占位）。
    # False 回退到旧的“纯文本切片 + 独立 image_description 向量”双路流水线。
    kb_markdown_pipeline: bool = True

    # 独立轻量起诉状生成：不依赖 OA 案件、审批或旧 generation run。
    drafting_lite_enabled: bool = True
    drafting_lite_data_root: str = "/drafting-lite"
    drafting_lite_retention_hours: int = 24
    drafting_lite_max_files: int = 10
    drafting_lite_max_total_bytes: int = 100 * 1024 * 1024
    drafting_lite_workers: int = 2
    drafting_lite_max_visual_pages: int = 100
    drafting_lite_cause_threshold: float = 0.55
    drafting_lite_llm_max_tokens: int = 4000
    drafting_lite_template_root: str = "/templates"
    drafting_lite_renderer_url: str = "http://document-renderer:8010"
    drafting_lite_renderer_token: str = ""


    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_with_search_path(self) -> str:
        # search_path 固定到 {pg_schema},public；URL 编码：空格 %20、= %3D、逗号 %2C
        # （逗号必须编码，否则被 query string 当参数分隔符）
        return (
            f"{self.database_url}?options=-c%20search_path%3D{self.pg_schema}%2Cpublic"
        )

    @property
    def vl_configured(self) -> bool:
        return bool(
            self.vl_enabled
            and self.vl_api_base
            and self.vl_effective_api_key
            and self.vl_model
        )

    @property
    def vl_effective_api_key(self) -> str:
        """VL 可单配密钥；同属百炼时安全复用现有 LLM 环境变量。"""
        return self.vl_api_key or self.llm_api_key

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_allowed_origins.split(",") if value.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.trusted_hosts.split(",") if value.strip()]

    @property
    def admin_role_codes(self) -> frozenset[str]:
        return frozenset(
            value.strip().lower()
            for value in self.auth_admin_role_codes.split(",")
            if value.strip()
        )

    @property
    def auth_configuration_status(self) -> str:
        if not self.auth_enabled:
            return "disabled" if not self.is_production else "misconfigured"
        return "ok" if len(self.rag_service_token.strip()) >= 32 else "misconfigured"

    @model_validator(mode="after")
    def validate_security_configuration(self):
        env = self.app_env.strip().lower()
        if env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if self.max_request_body_bytes < 1024:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be at least 1024")
        return self


settings = Settings()
