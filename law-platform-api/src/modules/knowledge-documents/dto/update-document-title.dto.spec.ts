import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import { UpdateDocumentTitleDto } from './update-document-title.dto';

describe('UpdateDocumentTitleDto', () => {
  it('trims a valid title', async () => {
    const dto = plainToInstance(UpdateDocumentTitleDto, {
      title: '  新标题  ',
    });
    await expect(validate(dto)).resolves.toHaveLength(0);
    expect(dto.title).toBe('新标题');
  });

  it('rejects blank and overlong titles', async () => {
    const blank = plainToInstance(UpdateDocumentTitleDto, { title: '   ' });
    const overlong = plainToInstance(UpdateDocumentTitleDto, {
      title: '法'.repeat(256),
    });
    await expect(validate(blank)).resolves.not.toHaveLength(0);
    await expect(validate(overlong)).resolves.not.toHaveLength(0);
  });
});
