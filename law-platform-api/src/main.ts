import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';

// BigInt 默认无法被 JSON.stringify 序列化（会抛 TypeError）。
// 全局 patch：序列化为 string（附件 id / file_size 等大整数按字符串返回前端）。
(BigInt.prototype as unknown as { toJSON: () => string }).toJSON = function () {
  return String(this);
};

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  await app.listen(process.env.PORT ?? 3000, process.env.HOST ?? '127.0.0.1');
}
void bootstrap().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : 'unknown error';
  console.error(`应用启动失败: ${message}`);
  process.exitCode = 1;
});
