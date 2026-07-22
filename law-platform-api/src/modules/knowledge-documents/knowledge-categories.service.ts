import {
  BadRequestException,
  ConflictException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { randomUUID } from 'crypto';
import { PrismaService } from '../../core/prisma/prisma.service';
import { CreateKnowledgeCategoryDto } from './dto/create-knowledge-category.dto';
import { UpdateKnowledgeCategoryDto } from './dto/update-knowledge-category.dto';
import {
  KnowledgeCategoryNode,
  KnowledgeCategorySelection,
} from './knowledge-categories.types';

type CategoryRow = {
  id: bigint;
  category_code: string;
  category_name: string;
  aliases: unknown;
  parent_id: bigint | null;
  sort_order: number;
  assignable: boolean;
  sensitive: boolean;
  is_system: boolean;
  status: string;
  direct_document_count: bigint;
};

type CategoryRecord = Omit<KnowledgeCategoryNode, 'children'> & {
  bigintId: bigint;
  bigintParentId: bigint | null;
  children: CategoryRecord[];
};

@Injectable()
export class KnowledgeCategoriesService {
  constructor(private readonly prisma: PrismaService) {}

  async tree(
    includeInactive = false,
  ): Promise<{ items: KnowledgeCategoryNode[] }> {
    const rows = await this.prisma.$queryRaw<CategoryRow[]>(Prisma.sql`
      SELECT c.id, c.category_code, c.category_name, c.aliases, c.parent_id,
             c.sort_order, c.assignable, c.sensitive, c.is_system, c.status,
             COUNT(d.id)::bigint AS direct_document_count
      FROM oa.kb_category c
      LEFT JOIN oa.kb_document d
        ON d.category_id = c.id
       AND d.deleted_at IS NULL
       AND d.status = 'active'
      WHERE c.deleted_at IS NULL
        ${includeInactive ? Prisma.empty : Prisma.sql`AND c.status = 'active'`}
      GROUP BY c.id
      ORDER BY c.sort_order, c.id
    `);
    return { items: this.buildTree(rows) };
  }

  async create(
    dto: CreateKnowledgeCategoryDto,
  ): Promise<KnowledgeCategoryNode> {
    const name = this.normalizeName(dto.name);
    const aliases = this.normalizeAliases(dto.aliases);
    const parentId = this.optionalId(dto.parent_id);
    if (parentId !== null) await this.requireMutableParent(parentId);
    const sortOrder = await this.nextSortOrder(parentId);
    const code = `custom_${randomUUID().replaceAll('-', '')}`;
    try {
      const rows = await this.prisma.$queryRaw<
        Array<{ id: bigint }>
      >(Prisma.sql`
        INSERT INTO oa.kb_category (
          category_code, category_name, aliases, parent_id, sort_order,
          assignable, sensitive, is_system, status, created_at, updated_at
        ) VALUES (
          ${code}, ${name}, ${JSON.stringify(aliases)}::jsonb, ${parentId},
          ${sortOrder}, ${dto.assignable ?? true}, ${dto.sensitive ?? false},
          FALSE, 'active', NOW(), NOW()
        ) RETURNING id
      `);
      return this.requireNode(rows[0].id, true);
    } catch (error: unknown) {
      this.rethrowConstraint(error);
    }
  }

  async update(
    categoryId: bigint,
    dto: UpdateKnowledgeCategoryDto,
  ): Promise<KnowledgeCategoryNode> {
    const current = await this.requireRow(categoryId, true);
    if (current.is_system) {
      throw new ConflictException('系统分类不能修改');
    }
    const parentId =
      dto.parent_id === undefined
        ? current.parent_id
        : this.optionalId(dto.parent_id);
    if (parentId === categoryId) {
      throw new ConflictException('分类不能移动到自身');
    }
    if (parentId !== null) {
      if (dto.status === 'active' && current.status === 'inactive') {
        const parent = await this.requireRow(parentId, true);
        if (parent.status !== 'active') {
          throw new ConflictException('请先启用上级分类');
        }
      }
      await this.requireMutableParent(parentId);
      if (await this.isDescendant(categoryId, parentId)) {
        throw new ConflictException('分类不能移动到自己的后代节点');
      }
    }
    if (dto.status === 'inactive') await this.assertCanDeactivate(categoryId);
    const name =
      dto.name === undefined
        ? current.category_name
        : this.normalizeName(dto.name);
    const aliases =
      dto.aliases === undefined
        ? this.asAliases(current.aliases)
        : this.normalizeAliases(dto.aliases);
    try {
      await this.prisma.$transaction(async (tx) => {
        await tx.$executeRaw(Prisma.sql`
          UPDATE oa.kb_category
          SET category_name = ${name}, aliases = ${JSON.stringify(aliases)}::jsonb,
              parent_id = ${parentId},
              sort_order = ${dto.sort_order ?? current.sort_order},
              assignable = ${dto.assignable ?? current.assignable},
              sensitive = ${dto.sensitive ?? current.sensitive},
              status = ${dto.status ?? current.status}, updated_at = NOW()
          WHERE id = ${categoryId} AND deleted_at IS NULL
        `);
        if (name !== current.category_name) {
          await tx.$executeRaw(Prisma.sql`
            UPDATE oa.kb_document
            SET legal_category = ${name}, updated_at = NOW()
            WHERE category_id = ${categoryId}
              AND deleted_at IS NULL AND status = 'active'
          `);
        }
      });
      return this.requireNode(categoryId, true);
    } catch (error: unknown) {
      this.rethrowConstraint(error);
    }
  }

  async deactivate(categoryId: bigint): Promise<KnowledgeCategoryNode> {
    const current = await this.requireRow(categoryId, true);
    if (current.is_system) {
      throw new ConflictException('系统分类不能停用');
    }
    await this.assertCanDeactivate(categoryId);
    await this.prisma.$executeRaw(Prisma.sql`
      UPDATE oa.kb_category
      SET status = 'inactive', updated_at = NOW()
      WHERE id = ${categoryId} AND deleted_at IS NULL
    `);
    return this.requireNode(categoryId, true);
  }

  async requireAssignable(
    categoryId: bigint,
  ): Promise<KnowledgeCategorySelection> {
    const node = await this.requireNode(categoryId, true);
    if (node.status !== 'active') {
      throw new BadRequestException('所选分类已停用，请重新选择');
    }
    if (!node.assignable || node.is_system) {
      throw new BadRequestException('请选择允许归档文档的知识分类');
    }
    return {
      id: categoryId,
      name: node.name,
      path: node.path,
      pathIds: node.path_ids.map((id) => BigInt(id)),
      effectiveSensitive: node.effective_sensitive,
    };
  }

  private async requireNode(
    categoryId: bigint,
    includeInactive: boolean,
  ): Promise<KnowledgeCategoryNode> {
    const { items } = await this.tree(includeInactive);
    const stack = [...items];
    while (stack.length) {
      const node = stack.shift()!;
      if (node.id === categoryId.toString()) return node;
      stack.unshift(...node.children);
    }
    throw new NotFoundException('知识分类不存在');
  }

  private async requireRow(
    categoryId: bigint,
    includeInactive: boolean,
  ): Promise<CategoryRow> {
    const rows = await this.prisma.$queryRaw<CategoryRow[]>(Prisma.sql`
      SELECT c.id, c.category_code, c.category_name, c.aliases, c.parent_id,
             c.sort_order, c.assignable, c.sensitive, c.is_system, c.status,
             0::bigint AS direct_document_count
      FROM oa.kb_category c
      WHERE c.id = ${categoryId} AND c.deleted_at IS NULL
        ${includeInactive ? Prisma.empty : Prisma.sql`AND c.status = 'active'`}
    `);
    if (!rows[0]) throw new NotFoundException('知识分类不存在');
    return rows[0];
  }

  private async requireMutableParent(parentId: bigint): Promise<void> {
    const parent = await this.requireRow(parentId, false);
    if (parent.is_system) {
      throw new ConflictException('不能在系统分类下新增或移动分类');
    }
  }

  private async nextSortOrder(parentId: bigint | null): Promise<number> {
    const rows = await this.prisma.$queryRaw<
      Array<{ value: number }>
    >(Prisma.sql`
      SELECT COALESCE(MAX(sort_order), 0) + 10 AS value
      FROM oa.kb_category
      WHERE parent_id IS NOT DISTINCT FROM ${parentId}
        AND deleted_at IS NULL AND status = 'active'
    `);
    return Number(rows[0]?.value ?? 10);
  }

  private async isDescendant(
    rootId: bigint,
    candidateId: bigint,
  ): Promise<boolean> {
    const rows = await this.prisma.$queryRaw<
      Array<{ found: boolean }>
    >(Prisma.sql`
      WITH RECURSIVE descendants AS (
        SELECT id FROM oa.kb_category WHERE parent_id = ${rootId}
        UNION ALL
        SELECT child.id FROM oa.kb_category child
        JOIN descendants parent ON child.parent_id = parent.id
        WHERE child.deleted_at IS NULL
      )
      SELECT EXISTS(SELECT 1 FROM descendants WHERE id = ${candidateId}) AS found
    `);
    return Boolean(rows[0]?.found);
  }

  private async assertCanDeactivate(categoryId: bigint): Promise<void> {
    const rows = await this.prisma.$queryRaw<
      Array<{ child_count: bigint; document_count: bigint }>
    >(Prisma.sql`
      SELECT
        (SELECT COUNT(*) FROM oa.kb_category
         WHERE parent_id = ${categoryId} AND deleted_at IS NULL
           AND status = 'active')::bigint AS child_count,
        (SELECT COUNT(*) FROM oa.kb_document
         WHERE category_id = ${categoryId} AND deleted_at IS NULL
           AND status = 'active')::bigint AS document_count
    `);
    if (Number(rows[0]?.child_count ?? 0) > 0) {
      throw new ConflictException('该分类存在活动子分类，不能停用');
    }
    const documentCount = Number(rows[0]?.document_count ?? 0);
    if (documentCount > 0) {
      throw new ConflictException(
        `该分类仍有关联文档 ${documentCount} 份，请先移动或删除`,
      );
    }
  }

  private buildTree(rows: CategoryRow[]): KnowledgeCategoryNode[] {
    const records = new Map<string, CategoryRecord>();
    for (const row of rows) {
      records.set(row.id.toString(), {
        id: row.id.toString(),
        code: row.category_code,
        name: row.category_name,
        aliases: this.asAliases(row.aliases),
        parent_id: row.parent_id?.toString() ?? null,
        path: [],
        path_ids: [],
        depth: 0,
        sort_order: row.sort_order,
        assignable: row.assignable,
        sensitive: row.sensitive,
        effective_sensitive: row.sensitive,
        is_system: row.is_system,
        status: row.status === 'inactive' ? 'inactive' : 'active',
        direct_document_count: Number(row.direct_document_count),
        total_document_count: Number(row.direct_document_count),
        children: [],
        bigintId: row.id,
        bigintParentId: row.parent_id,
      });
    }
    const roots: CategoryRecord[] = [];
    for (const record of records.values()) {
      const parent = record.parent_id
        ? records.get(record.parent_id)
        : undefined;
      if (parent) parent.children.push(record);
      else roots.push(record);
    }
    const sort = (items: CategoryRecord[]) => {
      items.sort(
        (a, b) =>
          a.sort_order - b.sort_order || Number(a.bigintId - b.bigintId),
      );
      items.forEach((item) => sort(item.children));
    };
    sort(roots);
    const visit = (
      item: CategoryRecord,
      parentPath: string[],
      parentIds: string[],
      inheritedSensitive: boolean,
      ancestors: Set<string>,
    ): number => {
      if (ancestors.has(item.id))
        throw new ConflictException('知识分类树存在循环');
      const nextAncestors = new Set(ancestors).add(item.id);
      item.path = [...parentPath, item.name];
      item.path_ids = [...parentIds, item.id];
      item.depth = item.path.length;
      item.effective_sensitive = inheritedSensitive || item.sensitive;
      item.total_document_count =
        item.direct_document_count +
        item.children.reduce(
          (sum, child) =>
            sum +
            visit(
              child,
              item.path,
              item.path_ids,
              item.effective_sensitive,
              nextAncestors,
            ),
          0,
        );
      return item.total_document_count;
    };
    roots.forEach((root) => visit(root, [], [], false, new Set()));
    return roots.map((root) => this.publicNode(root));
  }

  private publicNode(record: CategoryRecord): KnowledgeCategoryNode {
    const { bigintId: _id, bigintParentId: _parent, ...node } = record;
    void _id;
    void _parent;
    return {
      ...node,
      children: record.children.map((child) => this.publicNode(child)),
    };
  }

  private normalizeName(value: string): string {
    const name = value.trim().replace(/\s+/g, ' ');
    if (!name) throw new BadRequestException('分类名称不能为空');
    return name;
  }

  private normalizeAliases(value?: string[]): string[] {
    return [
      ...new Set((value ?? []).map((item) => item.trim()).filter(Boolean)),
    ];
  }

  private asAliases(value: unknown): string[] {
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === 'string')
      : [];
  }

  private optionalId(value: string | null | undefined): bigint | null {
    if (value === null || value === undefined || value === '') return null;
    try {
      const id = BigInt(value);
      if (id <= 0) throw new Error('non-positive');
      return id;
    } catch {
      throw new BadRequestException('父分类 ID 必须为正整数');
    }
  }

  private rethrowConstraint(error: unknown): never {
    const message = error instanceof Error ? error.message : '';
    const databaseCode =
      error instanceof Prisma.PrismaClientKnownRequestError &&
      error.code === 'P2010' &&
      error.meta &&
      typeof error.meta.code === 'string'
        ? error.meta.code
        : '';
    if (
      databaseCode === '23505' ||
      message.includes('uk_kb_category_active_sibling_name')
    ) {
      throw new ConflictException('同一父分类下已存在同名分类');
    }
    throw error;
  }
}
