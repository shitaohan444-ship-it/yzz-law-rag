import { Injectable, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

/**
 * PrismaClient 封装：应用启动时连接、销毁时断开。
 * 事务边界由调用方控制（对齐 Python `get_db` autocommit=False 的语义），
 * 业务 service 用 `prisma.$transaction(async (tx) => {...})`。
 */
@Injectable()
export class PrismaService
  extends PrismaClient
  implements OnModuleInit, OnModuleDestroy
{
  async onModuleInit(): Promise<void> {
    await this.$connect();
  }

  async onModuleDestroy(): Promise<void> {
    await this.$disconnect();
  }
}
