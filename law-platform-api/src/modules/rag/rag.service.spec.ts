import {
  BadGatewayException,
  GatewayTimeoutException,
  HttpException,
} from '@nestjs/common';
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

describe('RagService', () => {
  let service: RagService;
  let fetchSpy: jest.SpiedFunction<typeof fetch>;
  let values: Record<string, unknown>;

  beforeEach(async () => {
    values = {
      RAG_API_BASE_URL: 'http://127.0.0.1:8000',
      RAG_API_TIMEOUT_MS: 1000,
      RAG_SERVICE_TOKEN: '',
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
        message: '检索或问答参数不符合要求',
      },
    } satisfies Partial<HttpException>);
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
        headers: { Authorization: 'Bearer internal-only' },
      }),
    );
  });

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

  it('proxies status and markdown reads without exposing upstream details', async () => {
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
      );

    await expect(service.getDocumentStatus('42')).resolves.toMatchObject({
      embedding_status: 'success',
    });
    await expect(service.getDocumentMarkdown('42')).resolves.toMatchObject({
      markdown: '# 测试文档',
    });
    expect(fetchSpy.mock.calls[0][1]?.method).toBe('GET');
    expect(fetchSpy.mock.calls[1][1]?.method).toBe('GET');
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

    await expect(service.getDocumentChunks('30', 1, 20)).resolves.toEqual(
      payload,
    );
    expect(fetchSpy.mock.calls[0][0]).toBe(
      'http://127.0.0.1:8000/documents/30/chunks?page=1&page_size=20',
    );
    expect(JSON.stringify(payload)).not.toContain('dense');
    expect(JSON.stringify(payload)).not.toContain('sparse');
  });
});
