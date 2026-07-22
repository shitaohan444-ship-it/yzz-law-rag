import { BadRequestException, ConflictException } from '@nestjs/common';
import { PrismaService } from '../../core/prisma/prisma.service';
import { KnowledgeCategoriesService } from './knowledge-categories.service';

const rows = [
  {
    id: BigInt(1),
    category_code: 'client_material',
    category_name: '当事人案件材料',
    aliases: [],
    parent_id: null,
    sort_order: 10,
    assignable: false,
    sensitive: true,
    is_system: false,
    status: 'active',
    direct_document_count: BigInt(1),
  },
  {
    id: BigInt(2),
    category_code: 'client_material_open',
    category_name: '未结案',
    aliases: [],
    parent_id: BigInt(1),
    sort_order: 10,
    assignable: true,
    sensitive: false,
    is_system: false,
    status: 'active',
    direct_document_count: BigInt(2),
  },
];

describe('KnowledgeCategoriesService', () => {
  it('builds recursive paths, inherited sensitivity, and descendant totals', async () => {
    const prisma = { $queryRaw: jest.fn().mockResolvedValue(rows) };
    const service = new KnowledgeCategoriesService(
      prisma as unknown as PrismaService,
    );

    const tree = await service.tree();

    expect(tree.items[0]).toMatchObject({
      path: ['当事人案件材料'],
      direct_document_count: 1,
      total_document_count: 3,
      effective_sensitive: true,
    });
    expect(tree.items[0].children[0]).toMatchObject({
      path: ['当事人案件材料', '未结案'],
      depth: 2,
      effective_sensitive: true,
      total_document_count: 2,
    });
  });

  it('allows assigning an inherited sensitive category without a separate LAN confirmation', async () => {
    const prisma = { $queryRaw: jest.fn().mockResolvedValue(rows) };
    const service = new KnowledgeCategoriesService(
      prisma as unknown as PrismaService,
    );

    await expect(service.requireAssignable(BigInt(2))).resolves.toMatchObject({
      id: BigInt(2),
      name: '未结案',
      effectiveSensitive: true,
    });
  });

  it('protects the system uncategorized node from deactivation', async () => {
    const prisma = {
      $queryRaw: jest
        .fn()
        .mockResolvedValue([{ ...rows[0], id: BigInt(5), is_system: true }]),
    };
    const service = new KnowledgeCategoriesService(
      prisma as unknown as PrismaService,
    );

    await expect(service.deactivate(BigInt(5))).rejects.toBeInstanceOf(
      ConflictException,
    );
  });

  it('rejects assigning a document to an inactive category with a safe validation error', async () => {
    const prisma = {
      $queryRaw: jest
        .fn()
        .mockResolvedValue([
          { ...rows[1], status: 'inactive', direct_document_count: BigInt(0) },
        ]),
    };
    const service = new KnowledgeCategoriesService(
      prisma as unknown as PrismaService,
    );

    try {
      await service.requireAssignable(BigInt(2));
      throw new Error('expected inactive category validation to fail');
    } catch (error: unknown) {
      expect(error).toBeInstanceOf(BadRequestException);
      expect((error as BadRequestException).getResponse()).toMatchObject({
        message: '所选分类已停用，请重新选择',
      });
    }
  });

  it('requires an inactive parent to be re-enabled before its child', async () => {
    const inactiveChild = { ...rows[1], status: 'inactive' };
    const inactiveParent = { ...rows[0], status: 'inactive' };
    const prisma = {
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([inactiveChild])
        .mockResolvedValueOnce([inactiveParent]),
    };
    const service = new KnowledgeCategoriesService(
      prisma as unknown as PrismaService,
    );

    try {
      await service.update(BigInt(2), { status: 'active' });
      throw new Error('expected inactive parent validation to fail');
    } catch (error: unknown) {
      expect(error).toBeInstanceOf(ConflictException);
      expect((error as ConflictException).getResponse()).toMatchObject({
        message: '请先启用上级分类',
      });
    }
  });

  it('deactivates by status update without physically deleting the category row', async () => {
    const activeLeaf = { ...rows[1], direct_document_count: BigInt(0) };
    const inactiveLeaf = { ...activeLeaf, status: 'inactive' };
    let executedQuery: unknown;
    const execute = jest.fn((query: unknown) => {
      executedQuery = query;
      return Promise.resolve(1);
    });
    const prisma = {
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([activeLeaf])
        .mockResolvedValueOnce([
          { child_count: BigInt(0), document_count: BigInt(0) },
        ])
        .mockResolvedValueOnce([inactiveLeaf]),
      $executeRaw: execute,
    };
    const service = new KnowledgeCategoriesService(
      prisma as unknown as PrismaService,
    );

    await expect(service.deactivate(BigInt(2))).resolves.toMatchObject({
      id: '2',
      status: 'inactive',
    });
    const statement = executedQuery as { strings: string[] };
    expect(statement.strings.join(' ')).toContain("SET status = 'inactive'");
    expect(statement.strings.join(' ')).not.toContain('DELETE FROM');
  });

  it('reports the real remaining document count when deactivation is blocked', async () => {
    const activeLeaf = { ...rows[1], direct_document_count: BigInt(2) };
    const prisma = {
      $queryRaw: jest
        .fn()
        .mockResolvedValueOnce([activeLeaf])
        .mockResolvedValueOnce([
          { child_count: BigInt(0), document_count: BigInt(2) },
        ]),
    };
    const service = new KnowledgeCategoriesService(
      prisma as unknown as PrismaService,
    );

    await expect(service.deactivate(BigInt(2))).rejects.toThrow(
      '该分类仍有关联文档 2 份，请先移动或删除',
    );
  });
});
