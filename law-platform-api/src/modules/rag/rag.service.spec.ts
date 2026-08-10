import { BadGatewayException, GatewayTimeoutException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';
import { RagService } from './rag.service';

const searchPayload = {
  query: '试用期工资',
  total: 1,
  hits: [
    {
      chunk_id: 'doc-1-0',
      doc_id: 1,
      doc_title: '劳动合同法',
      source: '劳动合同法.md',
      chunk_idx: 0,
      text: '劳动者在试用期的工资不得低于约定工资的百分之八十。',
      score: 0.98,
    },
  ],
};

const officialLink = {
  provider: 'npc_flk',
  source_name: '国家法律法规数据库',
  label: '官网最新版',
  url: 'https://flk.npc.gov.cn/detail?id=0123456789abcdef0123456789abcdef',
};

const chatPayload = {
  question: '试用期工资是多少？',
  answer: '不得低于约定工资的百分之八十。[1]',
  refs: [],
  chat_log_id: null,
  hits_count: 0,
};

describe('RagService', () => {
  let service: RagService;
  let fetchSpy: jest.SpiedFunction<typeof fetch>;
  let values: Record<string, unknown>;

  beforeEach(async () => {
    values = {
      RAG_API_BASE_URL: 'http://127.0.0.1:8000',
      RAG_API_TIMEOUT_MS: 1000,
      RAG_SERVICE_TOKEN: '',
      RAG_DOCUMENT_API_BASE_URL: '',
      RAG_DOCUMENT_SERVICE_TOKEN: '',
      RAG_DOCUMENT_MAC_ALLOWLIST: '',
    };
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        RagService,
        {
          provide: ConfigService,
          useValue: { get: (key: string) => values[key] },
        },
      ],
    }).compile();
    service = module.get(RagService);
    fetchSpy = jest.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it('forwards only allowlisted search fields without an empty token', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify(searchPayload), { status: 200 }),
    );

    await expect(
      service.search({ query: '试用期工资', top_k: 5, doc_ids: [1] }),
    ).resolves.toEqual(searchPayload);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:8000/search');
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(typeof init?.body).toBe('string');
    expect(JSON.parse(init?.body as string)).toEqual({
      query: '试用期工资',
      top_k: 5,
      doc_ids: [1],
    });
  });

  it('accepts and transparently forwards validated official links', async () => {
    const payload = {
      ...searchPayload,
      hits: [{ ...searchPayload.hits[0], official_link: officialLink }],
    };
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    await expect(service.search({ query: '试用期工资' })).resolves.toEqual(
      payload,
    );
  });

  it.each([
    'http://flk.npc.gov.cn/detail?id=0123456789abcdef0123456789abcdef',
    'https://example.com/detail?id=0123456789abcdef0123456789abcdef',
    'javascript:alert(1)',
    'https://flk.npc.gov.cn/detail?id=bad',
  ])('rejects an unsafe official link: %s', async (url) => {
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({
          ...searchPayload,
          hits: [
            {
              ...searchPayload.hits[0],
              official_link: { ...officialLink, url },
            },
          ],
        }),
        { status: 200 },
      ),
    );
    await expect(service.search({ query: 'x' })).rejects.toMatchObject({
      status: 502,
      response: { code: 'RAG_INVALID_RESPONSE' },
    });
  });

  it('adds the internal token from server configuration only', async () => {
    values.RAG_SERVICE_TOKEN = 'server-secret-token';
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify(searchPayload), { status: 200 }),
    );

    await service.search({ query: '试用期工资' });

    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer server-secret-token',
    });
    expect(JSON.stringify(searchPayload)).not.toContain('server-secret-token');
  });

  it('preserves safe upstream validation status without exposing details', async () => {
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ detail: 'Authorization: Bearer leaked-secret' }),
        { status: 422 },
      ),
    );

    await expect(service.search({ query: 'x' })).rejects.toMatchObject({
      status: 422,
      response: {
        code: 'RAG_REQUEST_REJECTED',
        message: '知识库请求参数不符合要求',
      },
    });
  });

  it('retries transient connection errors then maps to 502 when exhausted', async () => {
    fetchSpy.mockRejectedValue(new Error('ECONNREFUSED'));
    await expect(service.search({ query: 'x' })).rejects.toBeInstanceOf(
      BadGatewayException,
    );
    expect(fetchSpy).toHaveBeenCalledTimes(3);
  });

  it('recovers when a retried connection succeeds on a later attempt', async () => {
    fetchSpy
      .mockRejectedValueOnce(new Error('ECONNRESET'))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(searchPayload), { status: 200 }),
      );
    await expect(service.search({ query: 'x' })).resolves.toBeDefined();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it('maps invalid JSON to 502 without retrying', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('not-json', { status: 200 }));
    await expect(service.search({ query: 'x' })).rejects.toMatchObject({
      status: 502,
      response: { code: 'RAG_INVALID_RESPONSE' },
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('maps aborted requests to 504', async () => {
    values.RAG_API_TIMEOUT_MS = 5;
    fetchSpy.mockImplementation(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'));
          });
        }),
    );

    await expect(service.search({ query: 'x' })).rejects.toBeInstanceOf(
      GatewayTimeoutException,
    );
  });

  it('proxies document ingest with the dedicated timeout and server token', async () => {
    values.RAG_SERVICE_TOKEN = 'internal-only';
    values.RAG_INGEST_TIMEOUT_MS = 900000;
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({
          doc_id: 42,
          status: 'success',
          chunk_count: 7,
          image_total: 0,
          image_kept: 0,
          image_filtered: 0,
          vl_status: 'success',
          message: '',
        }),
        { status: 200 },
      ),
    );

    await expect(service.ingestDocument('42', true)).resolves.toMatchObject({
      doc_id: 42,
      status: 'success',
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/documents/42/ingest?force=true',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer internal-only',
          'X-Request-ID': expect.any(String),
        }),
      }),
    );
  });

  it('falls back to the query URL and token when the document URL is absent', async () => {
    values.RAG_SERVICE_TOKEN = 'legacy-token';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42', false);

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://127.0.0.1:8000/documents/42/ingest?force=false',
    );
    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer legacy-token',
      }),
    );
  });

  it('falls back to the query token when the document token is absent', async () => {
    values.RAG_SERVICE_TOKEN = 'legacy-token';
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42', false);

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://192.168.0.243:18000/documents/42/ingest?force=false',
    );
    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer legacy-token',
      }),
    );
  });

  it('keeps search and chat on the query URL when document routing is configured', async () => {
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_ROUTE_MODE = 'initial_mac';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    fetchSpy
      .mockResolvedValueOnce(
        new Response(JSON.stringify(searchPayload), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(chatPayload), { status: 200 }),
      );

    await service.search({ query: '试用期工资' });
    await service.chat({ question: '试用期工资是多少？' });

    expect(fetchSpy.mock.calls[0][0]).toBe('http://127.0.0.1:8000/search');
    expect(fetchSpy.mock.calls[1][0]).toBe('http://127.0.0.1:8000/chat');
  });

  it('defaults an absent route mode to the existing allowlist behavior', async () => {
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000/';
    values.RAG_DOCUMENT_SERVICE_TOKEN = 'mac-token';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    const result = await service.ingestDocument('42', false);

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://192.168.0.243:18000/documents/42/ingest?force=false',
    );
    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer mac-token',
        'X-Request-ID': result.request_id,
      }),
    );
  });

  it('keeps non-allowlisted documents on the legacy URL', async () => {
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_ROUTE_MODE = 'allowlist';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '99';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42', false);

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://127.0.0.1:8000/documents/42/ingest?force=false',
    );
  });

  it('keeps an initial ingest on the legacy RAG in legacy mode', async () => {
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_ROUTE_MODE = 'legacy';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42', false);

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://127.0.0.1:8000/documents/42/ingest?force=false',
    );
  });

  it('routes force=false ingestion to the Mac in initial_mac mode without an allowlist', async () => {
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_SERVICE_TOKEN = 'mac-token';
    values.RAG_DOCUMENT_ROUTE_MODE = 'initial_mac';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42', false);

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://192.168.0.243:18000/documents/42/ingest?force=false',
    );
    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual(
      expect.objectContaining({ Authorization: 'Bearer mac-token' }),
    );
  });

  it('treats an omitted force argument as force=false in initial_mac mode', async () => {
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_ROUTE_MODE = 'initial_mac';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42');

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://192.168.0.243:18000/documents/42/ingest?force=false',
    );
  });

  it('keeps force=true ingestion on the legacy RAG in initial_mac mode', async () => {
    values.RAG_API_BASE_URL = 'http://127.0.0.1:8000';
    values.RAG_SERVICE_TOKEN = 'legacy-token';
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_SERVICE_TOKEN = 'mac-token';
    values.RAG_DOCUMENT_ROUTE_MODE = 'initial_mac';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42', true);

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://127.0.0.1:8000/documents/42/ingest?force=true',
    );
    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual(
      expect.objectContaining({ Authorization: 'Bearer legacy-token' }),
    );
  });

  it('routes every mutation to the Mac only in mac mode', async () => {
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_ROUTE_MODE = 'mac';
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42', true);

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://192.168.0.243:18000/documents/42/ingest?force=true',
    );
  });

  it('reuses one X-Request-ID for retries without falling back to legacy RAG', async () => {
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_ROUTE_MODE = 'initial_mac';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '';
    fetchSpy.mockRejectedValue(new Error('ECONNRESET'));

    await expect(service.ingestDocument('42', false)).rejects.toMatchObject({
      status: 502,
      response: {
        code: 'RAG_UNAVAILABLE',
        request_id: expect.any(String),
      },
    });

    expect(fetchSpy).toHaveBeenCalledTimes(3);
    const requestIds = fetchSpy.mock.calls.map(
      ([, init]) =>
        (init?.headers as Record<string, string> | undefined)?.['X-Request-ID'],
    );
    expect(new Set(requestIds).size).toBe(1);
    for (const [url] of fetchSpy.mock.calls) {
      expect(String(url)).toMatch(/^http:\/\/192\.168\.0\.243:18000\//);
    }
  });

  it.each([401, 403, 409, 503])(
    'preserves document upstream status %s with a sanitized response',
    async (status) => {
      values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
      values.RAG_DOCUMENT_ROUTE_MODE = 'initial_mac';
      values.RAG_DOCUMENT_MAC_ALLOWLIST = '';
      fetchSpy.mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: 'C:\\secret\\case.pdf postgres://user:password@db',
          }),
          { status },
        ),
      );

      let caught: unknown;
      try {
        await service.ingestDocument('42', false);
      } catch (error: unknown) {
        caught = error;
      }
      expect(caught).toMatchObject({
        status,
        response: {
          code: 'RAG_REQUEST_REJECTED',
          request_id: expect.any(String),
        },
      });
      expect(JSON.stringify(caught)).not.toMatch(/secret|postgres|password/i);
    },
  );

  it('forwards switches that disable paid ingestion stages for one job', async () => {
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 3 }),
        { status: 200 },
      ),
    );

    await service.ingestDocument('42', false, {
      generateDescription: false,
      analyzeImages: false,
    });

    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://127.0.0.1:8000/documents/42/ingest?force=false&generate_description=false&analyze_images=false',
    );
  });

  it('keeps allowlisted document status and previews on the query RAG', async () => {
    values.RAG_SERVICE_TOKEN = 'legacy-token';
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_SERVICE_TOKEN = 'mac-token';
    values.RAG_DOCUMENT_ROUTE_MODE = 'initial_mac';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    fetchSpy
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            doc_id: 42,
            embedding_status: 'success',
            chunk_count: 7,
            doc_title: '测试文档',
            vl_status: 'success',
            image_total: 0,
            image_kept: 0,
            image_filtered: 0,
            vl_processed_at: null,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            doc_id: 42,
            doc_title: '测试文档',
            description_summary: null,
            image_count: 0,
            markdown: '# 测试文档',
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            doc_id: 42,
            doc_title: '测试文档',
            total: 0,
            page: 1,
            page_size: 20,
            items: [],
          }),
          { status: 200 },
        ),
      );

    await expect(service.getDocumentStatus('42')).resolves.toMatchObject({
      embedding_status: 'success',
    });
    await expect(service.getDocumentMarkdown('42')).resolves.toMatchObject({
      markdown: '# 测试文档',
    });
    await expect(service.getDocumentChunks('42', 1, 20)).resolves.toMatchObject(
      {
        items: [],
      },
    );
    expect(fetchSpy.mock.calls[0][1]?.method).toBe('GET');
    expect(fetchSpy.mock.calls[1][1]?.method).toBe('GET');
    expect(fetchSpy.mock.calls[2][1]?.method).toBe('GET');
    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://127.0.0.1:8000/documents/42',
    );
    expect(fetchSpy.mock.calls[1][0]).toBe(
      'http://127.0.0.1:8000/documents/42/markdown',
    );
    expect(fetchSpy.mock.calls[2][0]).toBe(
      'http://127.0.0.1:8000/documents/42/chunks?page=1&page_size=20',
    );
    for (const [, init] of fetchSpy.mock.calls) {
      const headers = init?.headers as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer legacy-token');
      expect(headers['X-Request-ID']).toEqual(expect.any(String));
      expect(headers['X-RAG-User-Id']).toBeUndefined();
    }
  });

  it('keeps every document mutation route on the Mac target for an allowlisted document', async () => {
    values.RAG_SERVICE_TOKEN = 'legacy-token';
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_SERVICE_TOKEN = 'mac-token';
    values.RAG_DOCUMENT_ROUTE_MODE = 'allowlist';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    const logger = (
      service as unknown as {
        logger: {
          log(message: string): void;
          warn(message: string): void;
        };
      }
    ).logger;
    const logSpy = jest
      .spyOn(logger, 'log')
      .mockImplementation(() => undefined);
    const warnSpy = jest
      .spyOn(logger, 'warn')
      .mockImplementation(() => undefined);
    fetchSpy
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            doc_id: 42,
            source_id: 7,
            status: 'success',
            chunk_count: 1,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'deleted' }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [
              {
                doc_id: 42,
                ok: true,
                missing_chunks: 0,
                missing_images: [],
              },
            ],
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'cleaned' }), { status: 200 }),
      );

    await service.promoteDocument('99', '42');
    await service.promoteSource({
      stagingDocId: '99',
      targetDocId: '42',
      sourceId: '7',
      mode: 'append',
    });
    await service.rebuildSources('42', [{ sourceId: '7', stagingDocId: '99' }]);
    await service.batchDeleteDocuments(['42']);
    await service.verifyRestoreDocuments(['42']);
    await service.cleanupStagingDocument('99', '42');

    expect(fetchSpy.mock.calls.map(([url]) => url)).toEqual([
      'http://192.168.0.243:18000/documents/99/promote?target_doc_id=42',
      'http://192.168.0.243:18000/documents/99/promote-source',
      'http://192.168.0.243:18000/documents/rebuild-sources',
      'http://192.168.0.243:18000/documents/batch-delete',
      'http://192.168.0.243:18000/documents/verify-restore',
      'http://192.168.0.243:18000/documents/99/staging',
    ]);
    expect(fetchSpy.mock.calls.map(([, init]) => init?.method)).toEqual([
      'POST',
      'POST',
      'POST',
      'POST',
      'POST',
      'DELETE',
    ]);
    for (const [, init] of fetchSpy.mock.calls) {
      const headers = init?.headers as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer mac-token');
      expect(headers['X-Request-ID']).toEqual(expect.any(String));
      expect(headers['X-RAG-User-Id']).toBeUndefined();
    }
    expect(JSON.stringify(logSpy.mock.calls)).not.toContain('mac-token');
    expect(JSON.stringify(warnSpy.mock.calls)).not.toContain('mac-token');
    logSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it('keeps every advanced mutation on the legacy target in initial_mac mode', async () => {
    values.RAG_SERVICE_TOKEN = 'legacy-token';
    values.RAG_DOCUMENT_API_BASE_URL = 'http://192.168.0.243:18000';
    values.RAG_DOCUMENT_SERVICE_TOKEN = 'mac-token';
    values.RAG_DOCUMENT_ROUTE_MODE = 'initial_mac';
    values.RAG_DOCUMENT_MAC_ALLOWLIST = '42';
    const logger = (
      service as unknown as {
        logger: {
          log(message: string): void;
          warn(message: string): void;
        };
      }
    ).logger;
    const logSpy = jest
      .spyOn(logger, 'log')
      .mockImplementation(() => undefined);
    const warnSpy = jest
      .spyOn(logger, 'warn')
      .mockImplementation(() => undefined);
    fetchSpy
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            doc_id: 42,
            source_id: 7,
            status: 'success',
            chunk_count: 1,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ doc_id: 42, status: 'success', chunk_count: 1 }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'deleted' }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [
              {
                doc_id: 42,
                ok: true,
                missing_chunks: 0,
                missing_images: [],
              },
            ],
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'cleaned' }), { status: 200 }),
      );

    await service.promoteDocument('99', '42');
    await service.promoteSource({
      stagingDocId: '99',
      targetDocId: '42',
      sourceId: '7',
      mode: 'append',
    });
    await service.rebuildSources('42', [{ sourceId: '7', stagingDocId: '99' }]);
    await service.batchDeleteDocuments(['42']);
    await service.verifyRestoreDocuments(['42']);
    await service.cleanupStagingDocument('99', '42');

    expect(fetchSpy.mock.calls.map(([url]) => url)).toEqual([
      'http://127.0.0.1:8000/documents/99/promote?target_doc_id=42',
      'http://127.0.0.1:8000/documents/99/promote-source',
      'http://127.0.0.1:8000/documents/rebuild-sources',
      'http://127.0.0.1:8000/documents/batch-delete',
      'http://127.0.0.1:8000/documents/verify-restore',
      'http://127.0.0.1:8000/documents/99/staging',
    ]);
    for (const [, init] of fetchSpy.mock.calls) {
      const headers = init?.headers as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer legacy-token');
      expect(headers['X-Request-ID']).toEqual(expect.any(String));
    }
    expect(JSON.stringify(logSpy.mock.calls)).not.toMatch(
      /legacy-token|mac-token/,
    );
    expect(JSON.stringify(warnSpy.mock.calls)).not.toMatch(
      /legacy-token|mac-token/,
    );
    logSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it('validates and proxies a paginated chunk page without vectors', async () => {
    const payload = {
      doc_id: 30,
      doc_title: '测试文档',
      total: 1,
      page: 1,
      page_size: 20,
      items: [
        {
          chunk_id: '30:m:0000',
          chunk_idx: 0,
          text: '切片正文',
          char_count: 4,
          source: '案例',
          article_no: null,
          chapter: null,
          content_type: 'markdown',
          image_id: null,
          page_no: null,
          image_category: null,
        },
      ],
    };
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );

    await expect(service.getDocumentChunks('30', 1, 20)).resolves.toMatchObject(
      payload,
    );
    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://127.0.0.1:8000/documents/30/chunks?page=1&page_size=20',
    );
    expect(JSON.stringify(payload)).not.toContain('dense');
    expect(JSON.stringify(payload)).not.toContain('sparse');
  });
});
