import AppNavigation from './AppNavigation';
import CategoryManager from './CategoryManager';

export default function CategoryManagementPage() {
  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">LAW RAG · 局域网验收版</p>
          <h1>法律知识检索台</h1>
          <p className="hero-copy">独立维护知识库分类结构，并逐份整理各分类下的现有文档。</p>
        </div>
        <div className="gateway-status" aria-label="连接方式：平台网关">
          <span aria-hidden="true" />
          经平台网关访问
        </div>
      </header>

      <main className="workspace">
        <AppNavigation active="categories" onSelect={() => {}} />
        <CategoryManager />
      </main>

      <footer>
        <span>分类移动只更新数据库，不重新生成知识库向量。</span>
        <span>所有入库资料自动面向当前局域网检索</span>
      </footer>
    </div>
  );
}
