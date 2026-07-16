import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import App from './App';
import { ChunkPreviewPage, MarkdownPreviewPage } from './KnowledgePreviewPages';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/knowledge/documents/:docId/markdown" element={<MarkdownPreviewPage />} />
        <Route path="/knowledge/documents/:docId/chunks" element={<ChunkPreviewPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
