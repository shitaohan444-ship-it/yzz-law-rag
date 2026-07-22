import type { KnowledgeCategoryNode } from './types';

export function flattenCategories(
  roots: KnowledgeCategoryNode[],
): KnowledgeCategoryNode[] {
  return roots.flatMap((node) => [node, ...flattenCategories(node.children)]);
}

export function categoryLabel(node: KnowledgeCategoryNode): string {
  return node.path.join(' / ');
}

export function findCategory(
  roots: KnowledgeCategoryNode[],
  id: string,
): KnowledgeCategoryNode | undefined {
  return flattenCategories(roots).find((node) => node.id === id);
}

export function activeCategoryTree(
  roots: KnowledgeCategoryNode[],
): KnowledgeCategoryNode[] {
  return roots
    .filter((node) => node.status === 'active')
    .map((node) => ({
      ...node,
      children: activeCategoryTree(node.children),
    }));
}
