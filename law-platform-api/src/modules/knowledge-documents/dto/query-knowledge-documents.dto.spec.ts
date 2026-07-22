import 'reflect-metadata';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import { QueryKnowledgeDocumentsDto } from './query-knowledge-documents.dto';

describe('QueryKnowledgeDocumentsDto', () => {
  it.each([5, 10, 20, 50, 100, 500, 1000])(
    'accepts page_size=%i for the knowledge document selector',
    async (pageSize) => {
      const dto = plainToInstance(QueryKnowledgeDocumentsDto, {
        page: 1,
        page_size: pageSize,
      });
      await expect(validate(dto)).resolves.toHaveLength(0);
    },
  );

  it('rejects a page size above the supported selector maximum', async () => {
    const dto = plainToInstance(QueryKnowledgeDocumentsDto, {
      page: 1,
      page_size: 1001,
    });
    const errors = await validate(dto);
    expect(errors.some((error) => error.property === 'page_size')).toBe(true);
  });
});
