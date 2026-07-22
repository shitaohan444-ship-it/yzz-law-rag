export interface KnowledgeCategoryNode {
  id: string;
  code: string;
  name: string;
  aliases: string[];
  parent_id: string | null;
  path: string[];
  path_ids: string[];
  depth: number;
  sort_order: number;
  assignable: boolean;
  sensitive: boolean;
  effective_sensitive: boolean;
  is_system: boolean;
  status: 'active' | 'inactive';
  direct_document_count: number;
  total_document_count: number;
  children: KnowledgeCategoryNode[];
}

export interface KnowledgeCategorySelection {
  id: bigint;
  name: string;
  path: string[];
  pathIds: bigint[];
  effectiveSensitive: boolean;
}
