import { envValidationSchema } from './env.validation';

describe('envValidationSchema RAG document route mode', () => {
  const required = {
    DATABASE_URL: 'postgresql://user:password@localhost:5432/test',
    MINIO_ENDPOINT: 'localhost',
    MINIO_ACCESS_KEY: 'test-access',
    MINIO_SECRET_KEY: 'test-secret',
  };

  it.each(['legacy', 'allowlist', 'initial_mac', 'mac'])(
    'accepts %s',
    (mode) => {
      const result = envValidationSchema.validate({
        ...required,
        RAG_DOCUMENT_ROUTE_MODE: mode,
      });
      expect(result.error).toBeUndefined();
      expect(result.value.RAG_DOCUMENT_ROUTE_MODE).toBe(mode);
    },
  );

  it('defaults to allowlist when the mode is absent', () => {
    const result = envValidationSchema.validate(required);
    expect(result.error).toBeUndefined();
    expect(result.value.RAG_DOCUMENT_ROUTE_MODE).toBe('allowlist');
  });

  it('rejects an unsupported mode', () => {
    const result = envValidationSchema.validate({
      ...required,
      RAG_DOCUMENT_ROUTE_MODE: 'automatic',
    });
    expect(result.error).toBeDefined();
  });
});
