export type AppSection = 'search' | 'chat' | 'drafting' | 'knowledge' | 'categories' | 'trash';

interface Props {
  active: AppSection;
  onSelect: (section: AppSection) => void;
}

const items: { id: AppSection; label: string; description: string }[] = [
  { id: 'search', label: '法条检索', description: '查看原文片段' },
  { id: 'chat', label: '知识问答', description: '生成带引用回答' },
  { id: 'drafting', label: '智能起诉状', description: '上传材料自动生成' },
  { id: 'knowledge', label: '知识库管理', description: '上传并自动入库' },
  { id: 'categories', label: '分类管理', description: '逐级维护分类' },
  { id: 'trash', label: '回收站', description: '恢复或彻底删除' },
];

export default function AppNavigation({ active, onSelect }: Props) {
  return (
    <nav className="tabs" role="tablist" aria-label="RAG 功能">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={active === item.id}
          aria-controls={`${item.id}-panel`}
          id={`${item.id}-tab`}
          onClick={() => onSelect(item.id)}
        >
          {item.label}<small>{item.description}</small>
        </button>
      ))}
    </nav>
  );
}
