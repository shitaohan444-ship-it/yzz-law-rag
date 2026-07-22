import { useMemo } from 'react';
import { findCategory, flattenCategories } from './knowledgeCategories';
import type { KnowledgeCategoryNode } from './types';

interface Props {
  categories: KnowledgeCategoryNode[];
  value: string;
  onChange: (categoryId: string) => void;
  ariaPrefix: string;
  disabled?: boolean;
  includeSystem?: boolean;
  allowEmpty?: boolean;
  emptyLabel?: string;
  excludedIds?: Set<string>;
  className?: string;
  showPath?: boolean;
}

const chineseNumbers = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];

function levelLabel(index: number): string {
  return chineseNumbers[index] ? `${chineseNumbers[index]}级分类` : `第 ${index + 1} 级分类`;
}

export default function CategoryCascadeSelect({
  categories,
  value,
  onChange,
  ariaPrefix,
  disabled = false,
  includeSystem = false,
  allowEmpty = false,
  emptyLabel = '全部分类',
  excludedIds = new Set<string>(),
  className = '',
  showPath = true,
}: Props) {
  const flat = useMemo(() => flattenCategories(categories), [categories]);
  const selected = findCategory(categories, value);
  const selectedPath = selected
    ? selected.path_ids
        .map((id) => flat.find((node) => node.id === id))
        .filter((node): node is KnowledgeCategoryNode => Boolean(node))
    : [];

  const visible = (node: KnowledgeCategoryNode) =>
    (includeSystem || !node.is_system)
    && !excludedIds.has(node.id);

  const levels: KnowledgeCategoryNode[][] = [];
  const roots = categories.filter(visible);
  levels.push(roots);
  for (const node of selectedPath) {
    const children = node.children.filter(visible);
    if (children.length > 0) levels.push(children);
  }

  return (
    <div className={`category-cascade ${className}`.trim()}>
      {levels.map((nodes, index) => {
        const selectedAtLevel = selectedPath[index]?.id ?? '';
        const canBeEmpty = index === 0 ? allowEmpty : true;
        return (
          <label key={`${ariaPrefix}-${index}`}>
            <span>{levelLabel(index)}</span>
            <select
              aria-label={`${ariaPrefix}${levelLabel(index)}`}
              value={selectedAtLevel}
              disabled={disabled}
              onChange={(event) => {
                const nextId = event.target.value;
                if (nextId) onChange(nextId);
                else if (index === 0) onChange('');
                else onChange(selectedPath[index - 1]?.id ?? '');
              }}
            >
              {canBeEmpty && (
                <option value="">
                  {index === 0 ? emptyLabel : '不再选择下级分类'}
                </option>
              )}
              {!canBeEmpty && <option value="">请选择{levelLabel(index)}</option>}
              {nodes.map((node) => (
                <option key={node.id} value={node.id} disabled={node.status === 'inactive'}>
                  {node.name}{node.status === 'inactive' ? '（已停用，不可选择）' : node.assignable ? '' : '（不可直接归档）'}
                </option>
              ))}
            </select>
          </label>
        );
      })}
      {showPath && selected && (
        <small className="category-cascade-path">
          当前路径：{selected.path.join(' / ')}
          {!selected.assignable && ' · 请选择可直接归档的下级分类'}
        </small>
      )}
    </div>
  );
}
