import { INestApplication, ValidationPipe } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';
import type { Server } from 'node:http';
import request from 'supertest';
import { RagController } from '../src/modules/rag/rag.controller';
import { RagService } from '../src/modules/rag/rag.service';

describe('RAG gateway HTTP (e2e)', () => {
  let app: INestApplication;
  let server: Server;
  let fetchSpy: jest.SpiedFunction<typeof fetch>;

  beforeAll(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [RagController],
      providers: [
        RagService,
        {
          provide: ConfigService,
          useValue: {
            get: (key: string) =>
              ({
                RAG_API_BASE_URL: 'http://127.0.0.1:8000',
                RAG_API_TIMEOUT_MS: 1000,
                RAG_SERVICE_TOKEN: '',
              })[key],
          },
        },
      ],
    }).compile();
    app = module.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({ whitelist: true, transform: true }),
    );
    await app.init();
    server = app.getHttpServer() as Server;
  });

  beforeEach(() => {
    fetchSpy = jest.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  afterAll(async () => {
    await app.close();
  });

  it('POST /api/rag/search validates and returns the upstream result', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ query: '劳动合同', total: 0, hits: [] }), {
        status: 200,
      }),
    );

    const response = await request(server)
      .post('/api/rag/search')
      .send({ query: '劳动合同', top_k: 5, user_id: 999 });

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ query: '劳动合同', total: 0, hits: [] });
    const forwardedBody = fetchSpy.mock.calls[0][1]?.body;
    expect(typeof forwardedBody).toBe('string');
    expect(JSON.parse(forwardedBody as string)).toEqual({
      query: '劳动合同',
      top_k: 5,
    });
  });

  it('rejects empty queries and out-of-range top_k before forwarding', async () => {
    const empty = await request(server)
      .post('/api/rag/search')
      .send({ query: '' });
    const tooMany = await request(server)
      .post('/api/rag/chat')
      .send({ question: '问题', top_k: 21 });

    expect(empty.status).toBe(400);
    expect(tooMany.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('maps FastAPI 502 to a safe gateway error', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'provider API key leaked' }), {
        status: 502,
      }),
    );

    const response = await request(server)
      .post('/api/rag/chat')
      .send({ question: '产品缺陷造成损害怎么办' });

    expect(response.status).toBe(502);
    expect(response.body).toMatchObject({
      code: 'RAG_UPSTREAM_ERROR',
      message: '知识库服务处理失败，请稍后重试',
    });
    expect(JSON.stringify(response.body)).not.toContain('API key');
  });
});
