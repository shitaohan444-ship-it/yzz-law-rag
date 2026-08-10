import * as Joi from 'joi';

/**
 * 环境变量校验 schema（@nestjs/config 启动期校验，缺失/类型错误即启动失败）。
 */
export const envValidationSchema = Joi.object({
  NODE_ENV: Joi.string()
    .valid('development', 'production', 'test')
    .default('development'),
  PORT: Joi.number().default(3000),
  HOST: Joi.string().hostname().default('127.0.0.1'),

  // PostgreSQL（schema oa 由 prisma schemas 声明）
  DATABASE_URL: Joi.string().required(),

  // MinIO
  MINIO_ENDPOINT: Joi.string().required(),
  MINIO_PORT: Joi.number().default(9000),
  MINIO_ACCESS_KEY: Joi.string().required(),
  MINIO_SECRET_KEY: Joi.string().required(),
  MINIO_BUCKET: Joi.string().default('law-firm-files'),
  MINIO_USE_SSL: Joi.boolean().default(false),

  // FastAPI RAG 内部服务（只由平台网关访问）
  RAG_API_BASE_URL: Joi.string().uri().default('http://127.0.0.1:8000'),
  RAG_API_TIMEOUT_MS: Joi.number()
    .integer()
    .min(1000)
    .max(600000)
    .default(120000),
  RAG_INGEST_TIMEOUT_MS: Joi.number()
    .integer()
    .min(1000)
    .max(1800000)
    .default(900000),
  RAG_SERVICE_TOKEN: Joi.string().allow('').optional(),
  RAG_DOCUMENT_API_BASE_URL: Joi.string().uri().allow('').optional(),
  RAG_DOCUMENT_SERVICE_TOKEN: Joi.string().allow('').optional(),
  RAG_DOCUMENT_ROUTE_MODE: Joi.string()
    .valid('legacy', 'allowlist', 'initial_mac', 'mac')
    .default('allowlist'),
  RAG_DOCUMENT_MAC_ALLOWLIST: Joi.string().allow('').default(''),
  DRAFTING_LITE_GATEWAY_TIMEOUT_MS: Joi.number()
    .integer()
    .min(1000)
    .max(1800000)
    .default(900000),

  LEGAL_DRAFTING_WORKER_TOKEN: Joi.string().allow('').optional(),
  LEGAL_DRAFTING_RUN_TOKEN_SECRET: Joi.string().min(32).allow('').optional(),
  LEGAL_DRAFTING_LEASE_SECONDS: Joi.number()
    .integer()
    .min(30)
    .max(600)
    .default(120),
  LEGAL_DRAFTING_RUN_TOKEN_TTL_SECONDS: Joi.number()
    .integer()
    .min(900)
    .max(14400)
    .default(7200),
  LEGAL_DRAFTING_DEV_ACTOR_ID: Joi.string().default('1'),
});
