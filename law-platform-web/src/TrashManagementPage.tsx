import AppNavigation from './AppNavigation';
import TrashPage from './TrashPage';

export default function TrashManagementPage() {
  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">LAW RAG · RECYCLE BIN</p>
          <h1>法律知识检索台</h1>
          <p className="hero-copy">
            查看已软删除的知识库文档，按需恢复或永久删除。普通删除只标记状态，原件、图片与向量都会保留。
          </p>
        </div>
        <div className="gateway-status" aria-label="连接方式：平台网关">
          <span aria-hidden="true" />
          经平台网关访问
        </div>
      </header>

      <main className="workspace">
        <AppNavigation active="trash" />
        <TrashPage />
      </main>

      <footer>
        <span>恢复沿用当前知识库管理权限，永久删除不可恢复。</span>
        <span>所有入库资料自动面向当前局域网检索</span>
      </footer>
    </div>
  );
}
