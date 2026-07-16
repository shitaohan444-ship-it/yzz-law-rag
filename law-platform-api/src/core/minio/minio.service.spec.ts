import { ConfigService } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';
import { Readable } from 'node:stream';
import { MinioService } from './minio.service';

describe('MinioService', () => {
  let service: MinioService;
  let client: {
    bucketExists: jest.Mock;
    makeBucket: jest.Mock;
    statObject: jest.Mock;
    putObject: jest.Mock;
    getObject: jest.Mock;
    presignedGetObject: jest.Mock;
    presignedPutObject: jest.Mock;
    removeObject: jest.Mock;
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        MinioService,
        { provide: ConfigService, useValue: { get: jest.fn() } },
      ],
    }).compile();
    service = module.get(MinioService);
    client = {
      bucketExists: jest.fn(),
      makeBucket: jest.fn(),
      statObject: jest.fn(),
      putObject: jest.fn(),
      getObject: jest.fn(),
      presignedGetObject: jest.fn(),
      presignedPutObject: jest.fn(),
      removeObject: jest.fn(),
    };
    Reflect.set(service, 'bucketName', 'law-firm-files');
    Reflect.set(service, 'client', client);
  });

  it('uploads bytes and returns authoritative stat metadata', async () => {
    client.bucketExists.mockResolvedValue(false);
    client.makeBucket.mockResolvedValue(undefined);
    client.statObject
      .mockRejectedValueOnce({ code: 'NoSuchKey' })
      .mockResolvedValueOnce({ etag: 'etag-1', size: 3 });
    client.putObject.mockResolvedValue({});

    const result = await service.uploadFile('cases/a.pdf', Buffer.from('abc'));

    expect(client.makeBucket).toHaveBeenCalledWith('law-firm-files');
    expect(client.putObject).toHaveBeenCalledWith(
      'law-firm-files',
      'cases/a.pdf',
      expect.any(Buffer),
      3,
      { 'Content-Type': 'application/pdf' },
    );
    expect(result).toEqual({
      bucket: 'law-firm-files',
      objectKey: 'cases/a.pdf',
      etag: 'etag-1',
      size: 3,
    });
  });

  it('downloads stream bytes and creates GET/PUT presigned URLs', async () => {
    client.getObject.mockResolvedValue(
      Readable.from([Buffer.from('a'), Buffer.from('bc')]),
    );
    client.presignedGetObject.mockResolvedValue('https://minio/get');
    client.presignedPutObject.mockResolvedValue('https://minio/put');

    await expect(service.downloadFile('a.txt')).resolves.toEqual(
      Buffer.from('abc'),
    );
    await expect(service.getPresignedUrl('a.txt')).resolves.toBe(
      'https://minio/get',
    );
    await expect(
      service.getPresignedUrl('a.txt', { method: 'PUT', expires: 60 }),
    ).resolves.toBe('https://minio/put');
  });

  it('maps known missing-object errors to false', async () => {
    client.statObject.mockRejectedValue({ statusCode: 404 });

    await expect(service.fileExists('missing.pdf')).resolves.toBe(false);
  });

  it('propagates MinIO errors and delete promise rejection', async () => {
    const networkError = new Error('network unavailable');
    client.statObject.mockRejectedValue(networkError);
    client.removeObject.mockRejectedValue(networkError);

    await expect(service.fileExists('a.pdf')).rejects.toBe(networkError);
    await expect(service.deleteFile('a.pdf')).rejects.toBe(networkError);
  });
});
