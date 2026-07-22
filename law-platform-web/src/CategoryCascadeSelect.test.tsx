import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CategoryCascadeSelect from './CategoryCascadeSelect';
import type { KnowledgeCategoryNode } from './types';

const inactiveChild: KnowledgeCategoryNode = {
  id: '2', code: 'inactive', name: '停用分类', aliases: [], parent_id: '1',
  path: ['启用分类', '停用分类'], path_ids: ['1', '2'], depth: 2,
  sort_order: 20, assignable: true, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'inactive', direct_document_count: 0,
  total_document_count: 0, children: [],
};

const categories: KnowledgeCategoryNode[] = [{
  id: '1', code: 'active', name: '启用分类', aliases: [], parent_id: null,
  path: ['启用分类'], path_ids: ['1'], depth: 1,
  sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
  is_system: false, status: 'active', direct_document_count: 0,
  total_document_count: 0, children: [inactiveChild],
}];

describe('CategoryCascadeSelect', () => {
  afterEach(cleanup);

  it('shows inactive categories as disabled options with an explicit explanation', () => {
    render(
      <CategoryCascadeSelect
        categories={categories}
        value="1"
        onChange={vi.fn()}
        ariaPrefix="上传"
      />,
    );

    const secondLevel = screen.getByRole('combobox', { name: '上传二级分类' });
    expect(within(secondLevel).getByRole('option', { name: '停用分类（已停用，不可选择）' })).toBeDisabled();
    expect(screen.queryByText('停用分类不能用于上传、筛选或文档归类。')).not.toBeInTheDocument();
  });
});
