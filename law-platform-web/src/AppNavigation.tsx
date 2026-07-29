export type AppSection = 'search' | 'chat' | 'drafting' | 'knowledge' | 'categories' | 'trash';

interface Props {
  active: AppSection;
  onSelect?: (section: Exclude<AppSection, 'categories' | 'trash'>) => void;
}

const items = [
  { id: 'search' as const, label: '法条检索', description: '查看原文片段', href: '/?tab=search' },
  { id: 'chat' as const, label: '知识问答', description: '生成带引用回答', href: '/?tab=chat' },
  { id: 'drafting' as const, label: '智能起诉状', description: '上传材料自动生成', href: '/?tab=drafting' },
  { id: 'knowledge' as const, label: '知识库管理', description: '上传并自动入库', href: '/?tab=knowledge' },
  { id: 'categories' as const, label: '分类管理', description: '逐级维护分类', href: '/knowledge/categories' },
  { id: 'trash' as const, label: '回收站', description: '恢复或彻底删除', href: '/knowledge/trash' },
];

export default function AppNavigation({ active, onSelect }: Props) {
  return (
    <nav className="tabs" role="tablist" aria-label="RAG 功能">
      {items.map((item) => {
        const content = <>{item.label}<small>{item.description}</small></>;
        if (item.id !== 'categories' && item.id !== 'trash' && onSelect) {
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={active === item.id}
              aria-controls={`${item.id}-panel`}
              id={`${item.id}-tab`}
              onClick={() => onSelect(item.id)}
            >
              {content}
            </button>
          );
        }
        return (
          <a
            key={item.id}
            role="tab"
            id={`${item.id}-tab`}
            aria-controls={`${item.id}-panel`}
            aria-selected={active === item.id}
            href={item.href}
          >
            {content}
          </a>
        );
      })}
    </nav>
  );
}
