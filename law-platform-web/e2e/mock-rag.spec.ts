import { expect, test } from '@playwright/test';

test('mock RAG search and chat stay behind the platform gateway', async ({ page }) => {
  const directRagRequests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes(':8000')) directRagRequests.push(request.url());
  });
  await page.route('**/api/rag/search', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ query: '试用期工资最低不能少于多少', total: 1, hits: [{ chunk_id: '1-0', doc_id: 1, doc_title: '中华人民共和国劳动合同法', source: '劳动合同法.md', chunk_idx: 0, text: '劳动者在试用期的工资不得低于约定工资的百分之八十。', score: 0.98, article_no: '第二十条' }] }),
  }));
  await page.route('**/api/rag/chat', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ question: '产品缺陷造成损害生产厂家要赔吗', answer: '**需要承担责任。** [1]', refs: [{ ref_id: 1, chunk_id: '2-0', doc_id: 2, doc_title: '中华人民共和国民法典', source: '民法典.md', chunk_idx: 0, text: '生产者应当承担侵权责任。', score: 0.99, article_no: '第一千二百零二条' }], chat_log_id: 1, hits_count: 1 }),
  }));

  await page.goto('/');
  await page.getByLabel('检索问题').fill('试用期工资最低不能少于多少');
  await page.getByRole('button', { name: '开始检索' }).click();
  await expect(page.getByText('中华人民共和国劳动合同法')).toBeVisible();
  await expect(page.getByText('第二十条')).toBeVisible();
  await page.getByRole('tab', { name: /知识问答/ }).click();
  await page.getByLabel('法律问题').fill('产品缺陷造成损害生产厂家要赔吗');
  await page.getByRole('button', { name: '提交问题' }).click();
  await expect(page.getByText('需要承担责任。')).toBeVisible();
  await expect(page.getByText('第一千二百零二条').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  expect(directRagRequests).toEqual([]);
});

test('mock no-basis response is visibly marked', async ({ page }) => {
  await page.route('**/api/rag/chat', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ question: '盗窃数额较大的刑事量刑标准是什么', answer: '现有知识库中没有足够依据回答该问题。', refs: [], chat_log_id: null, hits_count: 0 }),
  }));
  await page.goto('/');
  await page.getByRole('tab', { name: /知识问答/ }).click();
  await page.getByLabel('法律问题').fill('盗窃数额较大的刑事量刑标准是什么');
  await page.getByRole('button', { name: '提交问题' }).click();
  await expect(page.getByText('知识库依据不足')).toBeVisible();
});

test('mock knowledge document supports append, source filtering, and source replacement', async ({ page }) => {
  const internalRequests: string[] = [];
  page.on('request', (request) => {
    if (/:(8000|9000|19530)\b/.test(request.url())) internalRequests.push(request.url());
  });
  let uploaded = false;
  let appended = false;
  let replaced = false;
  const listPageSizes: number[] = [];
  const baseDocument = {
    doc_id: '24', attachment_id: '56', title: '浏览器多源验收', category: '法规',
    embedding_status: 'success', file_name: 'main.md', file_size: '48', source_count: 1,
    image_total: 0, created_at: '2026-07-16T00:00:00.000Z', upload_timings: null, ingest_timings: null,
  };
  const primary = { source_id: '81', document_id: '24', attachment_id: '56', source_title: 'main.md', file_name: 'main.md', file_size: '48', sort_order: 0, is_primary: true, ingest_status: 'success', chunk_count: 1, image_total: 0, image_kept: 0, image_filtered: 0, upload_timings: null, ingest_timings: null };
  const followup = () => ({ source_id: '82', document_id: '24', attachment_id: '57', source_title: replaced ? '修订后来源' : '后续材料', file_name: replaced ? 'v3.md' : 'v2.md', file_size: '42', sort_order: 1, is_primary: false, ingest_status: 'success', chunk_count: 1, image_total: 0, image_kept: 0, image_filtered: 0, upload_timings: null, ingest_timings: null });

  await page.context().route('**/api/rag/documents**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() === 'GET' && path.endsWith('/24/sources')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: appended ? [primary, followup()] : [primary] }) });
      return;
    }
    if (request.method() === 'POST' && path.endsWith('/24/sources')) {
      appended = true;
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ document: { ...baseDocument, source_count: 2 }, source: followup(), chunk_count: 2 }) });
      return;
    }
    if (request.method() === 'PUT' && path.endsWith('/24/sources/82/file')) {
      replaced = true;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ document: { ...baseDocument, source_count: 2 }, source: followup(), chunk_count: 2 }) });
      return;
    }
    if (request.method() === 'GET' && path.endsWith('/24/chunks')) {
      const selected = url.searchParams.get('source_id');
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ doc_id: 24, doc_title: '浏览器多源验收', total: selected ? 1 : appended ? 2 : 1, page: 1, page_size: 20, items: [{ chunk_id: selected === '82' ? '24:s:82:m:0000' : '24:s:81:m:0000', chunk_idx: selected === '82' ? 1 : 0, text: selected === '82' ? '后续来源 Chunk' : '主文件 Chunk', char_count: 10, source: '法规', source_id: Number(selected || 81), source_title: selected === '82' ? followup().source_title : 'main.md', source_file_name: selected === '82' ? followup().file_name : 'main.md', source_chunk_idx: 0, article_no: null, chapter: null, content_type: 'markdown', image_id: null, page_no: null, image_category: null }] }) });
      return;
    }
    if (request.method() === 'GET' && path.endsWith('/24/markdown')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ doc_id: 24, doc_title: '浏览器多源验收', description_summary: null, image_count: 0, source_count: appended ? 2 : 1, source_id: url.searchParams.get('source_id') ? Number(url.searchParams.get('source_id')) : null, markdown: '# 来源文件\n\n测试正文' }) });
      return;
    }
    if (request.method() === 'GET' && path.endsWith('/24/status')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ doc_id: 24, embedding_status: 'success', chunk_count: appended ? 2 : 1, doc_title: '浏览器多源验收', vl_status: 'success', image_total: 0, image_kept: 0, image_filtered: 0, vl_processed_at: null }) });
      return;
    }
    if (request.method() === 'POST' && path.endsWith('/24/ingest')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ doc_id: 24, status: 'success', chunk_count: 1, image_total: 0, image_kept: 0, image_filtered: 0, vl_status: 'success', message: '' }) });
      return;
    }
    if (request.method() === 'GET') {
      const pageSize = Number(url.searchParams.get('page_size'));
      expect([5, 10, 20, 50, 100, 500, 1000]).toContain(pageSize);
      listPageSizes.push(pageSize);
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: uploaded ? [{ ...baseDocument, source_count: appended ? 2 : 1 }] : [], total: uploaded ? 1 : 0, page: 1, page_size: pageSize }) });
      return;
    }
    uploaded = true;
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ document: { ...baseDocument, embedding_status: 'pending' }, deduplicated: false }) });
  });

  await page.goto('/');
  await page.getByRole('tab', { name: /知识库管理/ }).click();
  await expect(page.getByRole('button', { name: '继续上传' })).toHaveCount(0);
  await page.getByLabel('选择文件').setInputFiles({ name: 'main.md', mimeType: 'text/markdown', buffer: Buffer.from('# main') });
  await page.getByLabel('文档标题').fill('浏览器多源验收');
  await page.getByRole('button', { name: '新建并自动入库' }).click();
  await expect(page.getByText(/已入库，共 1 个片段/)).toBeVisible();
  await expect(page.getByLabel('已登记文档每页数量')).toHaveValue('5');
  await page.getByLabel('已登记文档每页数量').selectOption('1000');
  await expect.poll(() => listPageSizes.includes(1000)).toBe(true);

  await page.getByRole('button', { name: '追加文件' }).click();
  await page.getByLabel('后续文件').setInputFiles({ name: 'v2.md', mimeType: 'text/markdown', buffer: Buffer.from('# v2') });
  await expect(page.getByLabel('来源标题')).toHaveValue('v2.md');
  await page.getByLabel('来源标题').fill('后续材料');
  await page.getByRole('button', { name: '确认追加文件' }).click();
  await expect(page.getByText(/当前共 2 个源文件、2 个 Chunk/)).toBeVisible();

  const markdownPopupPromise = page.waitForEvent('popup');
  await page.getByRole('link', { name: '查看 Markdown' }).click();
  const markdownPopup = await markdownPopupPromise;
  await expect(markdownPopup).toHaveURL(/\/knowledge\/documents\/24\/markdown$/);
  await expect(markdownPopup.getByText('测试正文')).toBeVisible();
  await markdownPopup.close();

  await page.getByRole('button', { name: '管理文件' }).click();
  await expect(page.getByRole('heading', { name: '后续材料' })).toBeVisible();
  const sourceCard = page.locator('.source-file-card').filter({ hasText: '后续材料' });
  const chunkPopupPromise = page.waitForEvent('popup');
  await sourceCard.getByRole('link', { name: '查看 Chunk' }).click();
  const chunkPopup = await chunkPopupPromise;
  await expect(chunkPopup).toHaveURL(/source_id=82.*page=1/);
  await expect(chunkPopup.getByText('24:s:82:m:0000')).toBeVisible();
  await expect(chunkPopup.getByLabel('Chunk 来源筛选')).toHaveValue('82');
  expect(await chunkPopup.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  await chunkPopup.close();

  await sourceCard.getByRole('button', { name: '替换文件' }).click();
  await expect(page.getByLabel('替换来源标题')).toHaveValue('后续材料');
  await page.getByLabel('新的源文件').setInputFiles({ name: 'v3.md', mimeType: 'text/markdown', buffer: Buffer.from('# v3') });
  await page.getByLabel('替换来源标题').fill('修订后来源');
  await page.getByRole('button', { name: '确认替换源文件' }).click();
  await expect(page.getByRole('heading', { name: '修订后来源' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  expect(internalRequests).toEqual([]);
});
