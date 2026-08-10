import { ValidationPipe } from '@nestjs/common';
import { SubmitUserInputsDto } from './create-generation.dto';

describe('SubmitUserInputsDto', () => {
  const pipe = new ValidationPipe({ whitelist: true, transform: true });

  it('keeps and normalizes input_version under whitelist validation', async () => {
    const dto = await pipe.transform(
      {
        input_version: '01',
        actor_id: '1',
        inputs: [
          {
            field_id: 'party.plaintiff.name',
            value: '钱七',
            resolution_type: 'confirmed',
          },
        ],
      },
      { type: 'body', metatype: SubmitUserInputsDto },
    );

    expect(dto.input_version).toBe(1);
    expect(dto.inputs[0]).toBeInstanceOf(Object);
    expect(dto.inputs[0].field_id).toBe('party.plaintiff.name');
  });
});
