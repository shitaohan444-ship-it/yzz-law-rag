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
    category_id: '2', category_name: '法律', category_path: ['法律法规', '法律'],
    category_path_ids: ['1', '2'], category_sensitive: true,
    embedding_status: 'success', file_name: 'main.md', file_size: '48', source_count: 1,
    image_total: 0, created_at: '2026-07-16T00:00:00.000Z', last_uploaded_at: '2026-07-16T01:00:00.000Z', upload_timings: null, ingest_timings: null,
  };
  const primary = { source_id: '81', document_id: '24', attachment_id: '56', source_title: 'main.md', file_name: 'main.md', file_size: '48', sort_order: 0, is_primary: true, ingest_status: 'success', chunk_count: 1, image_total: 0, image_kept: 0, image_filtered: 0, uploaded_at: '2026-07-16T01:00:00.000Z', upload_timings: null, ingest_timings: null };
  const followup = () => ({ source_id: '82', document_id: '24', attachment_id: '57', source_title: replaced ? '修订后来源' : '后续材料', file_name: replaced ? 'v3.md' : 'v2.md', file_size: '42', sort_order: 1, is_primary: false, ingest_status: 'success', chunk_count: 1, image_total: 0, image_kept: 0, image_filtered: 0, uploaded_at: replaced ? '2026-07-16T03:00:00.000Z' : '2026-07-16T02:00:00.000Z', upload_timings: null, ingest_timings: null });

  await page.route('**/api/rag/categories**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      items: [{
        id: '1', code: 'legal', name: '法律法规', aliases: [], parent_id: null,
        path: ['法律法规'], path_ids: ['1'], depth: 1, sort_order: 10,
        assignable: false, sensitive: false, effective_sensitive: false,
        is_system: false, status: 'active', direct_document_count: 0,
        total_document_count: 1, children: [{
          id: '2', code: 'legal_law', name: '法律', aliases: [], parent_id: '1',
          path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2,
          sort_order: 20, assignable: true, sensitive: true,
          effective_sensitive: true, is_system: false, status: 'active',
          direct_document_count: 1, total_document_count: 1, children: [],
        }, {
          id: '8', code: 'inactive_archive', name: '停用资料', aliases: [], parent_id: '1',
          path: ['法律法规', '停用资料'], path_ids: ['1', '8'], depth: 2,
          sort_order: 30, assignable: true, sensitive: false,
          effective_sensitive: false, is_system: false, status: 'inactive',
          direct_document_count: 0, total_document_count: 0, children: [],
        }],
      }],
    }),
  }));

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
  await expect(page.getByLabel('上传一级分类')).toHaveValue('1');
  await expect(page.getByLabel('上传二级分类')).toHaveValue('2');
  await expect(page.getByLabel('上传二级分类').locator('option[value="8"]')).toHaveAttribute('disabled', '');
  await expect(page.getByText('停用分类不能用于上传、筛选或文档归类。')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '分类管理' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '修改分类' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '继续上传' })).toHaveCount(0);
  await expect(page.getByText('我确认当前局域网使用者均可能检索此资料')).toHaveCount(0);
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

test('batch upload keeps full filenames, edits titles, and stays behind the gateway', async ({ page }) => {
  const internalRequests: string[] = [];
  const uploadedTitles: string[] = [];
  page.on('request', (request) => {
    if (/:(8000|9000|19530)\b/.test(request.url())) internalRequests.push(request.url());
  });
  const timestamp = '2026-07-20T08:30:15.123Z';
  const makeDocument = (id: string, title: string, status = 'pending') => ({
    doc_id: id, attachment_id: `a-${id}`, title, category: '法律法规 / 法律',
    category_id: '2', category_name: '法律', category_path: ['法律法规', '法律'],
    category_path_ids: ['1', '2'], category_sensitive: false,
    embedding_status: status, file_name: title, file_size: '20', source_count: 1,
    image_total: 0, created_at: timestamp, last_uploaded_at: timestamp,
    upload_timings: null, ingest_timings: null,
  });
  let createdDocument = makeDocument('31', '第一份.md');

  await page.route('**/api/rag/categories**', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: [{
      id: '1', code: 'legal', name: '法律法规', aliases: [], parent_id: null,
      path: ['法律法规'], path_ids: ['1'], depth: 1, sort_order: 10,
      assignable: false, sensitive: false, effective_sensitive: false,
      is_system: false, status: 'active', direct_document_count: 0,
      total_document_count: 1, children: [{
        id: '2', code: 'legal_law', name: '法律', aliases: [], parent_id: '1',
        path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2,
        sort_order: 20, assignable: true, sensitive: false,
        effective_sensitive: false, is_system: false, status: 'active',
        direct_document_count: 1, total_document_count: 1, children: [],
      }],
    }] }),
  }));

  await page.route('**/api/rag/documents**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() === 'GET' && path === '/api/rag/documents') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: uploadedTitles.length ? [{ ...createdDocument, embedding_status: 'success' }] : [], total: uploadedTitles.length ? 1 : 0, page: 1, page_size: 5 }) });
      return;
    }
    if (request.method() === 'POST' && path === '/api/rag/documents') {
      const body = request.postData() ?? '';
      const title = body.includes('第一份.md') ? '第一份.md' : '已有文件.pdf';
      uploadedTitles.push(title);
      const deduplicated = title === '已有文件.pdf';
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ document: deduplicated ? makeDocument('24', title, 'success') : createdDocument, deduplicated }) });
      return;
    }
    if (request.method() === 'POST' && path.endsWith('/31/ingest')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ doc_id: 31, status: 'success', chunk_count: 4, image_total: 0, image_kept: 0, image_filtered: 0, vl_status: 'success', message: '' }) });
      return;
    }
    if (request.method() === 'GET' && path.endsWith('/31/status')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ doc_id: 31, embedding_status: 'success', chunk_count: 4, doc_title: createdDocument.title, vl_status: 'success', image_total: 0, image_kept: 0, image_filtered: 0, vl_processed_at: null }) });
      return;
    }
    if (request.method() === 'PATCH' && path.endsWith('/31/title')) {
      const body = request.postDataJSON() as { title: string };
      createdDocument = { ...createdDocument, title: body.title };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(createdDocument) });
      return;
    }
    await route.abort();
  });

  await page.goto('/');
  await page.getByRole('tab', { name: /知识库管理/ }).click();
  await page.getByRole('tab', { name: '批量导入' }).click();
  await page.getByLabel('批量选择文件').setInputFiles([
    { name: '第一份.md', mimeType: 'text/markdown', buffer: Buffer.from('# one') },
    { name: '已有文件.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF mock') },
  ]);
  await page.getByRole('button', { name: '开始批量导入' }).click();
  await expect(page.getByText('入库成功').first()).toBeVisible();
  await expect(page.getByText('文件已存在').first()).toBeVisible();
  expect(uploadedTitles).toEqual(['第一份.md', '已有文件.pdf']);

  const firstRow = page.locator('.batch-file-row').filter({ hasText: '第一份.md' });
  await firstRow.getByRole('button', { name: '修改标题' }).click();
  await page.getByLabel('修改后的文档标题').fill('批量标题已修改');
  await page.getByRole('button', { name: '确认修改标题' }).click();
  await expect(firstRow.getByRole('heading', { name: '批量标题已修改' })).toBeVisible();
  await expect(firstRow.getByText(/最后上传/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  expect(internalRequests).toEqual([]);
});

test('category management is independent and separates every adjacent level', async ({ page }) => {
  const internalRequests: string[] = [];
  page.on('request', (request) => {
    if (/:(8000|9000|19530)\b/.test(request.url())) internalRequests.push(request.url());
  });
  const contract = {
    id: '4', code: 'labor_contract', name: '劳动合同', aliases: [], parent_id: '3',
    path: ['法律法规', '法律', '劳动法律', '劳动合同'], path_ids: ['1', '2', '3', '4'], depth: 4,
    sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
    is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0, children: [],
  };
  const labor = {
    id: '3', code: 'labor_law', name: '劳动法律', aliases: [], parent_id: '2',
    path: ['法律法规', '法律', '劳动法律'], path_ids: ['1', '2', '3'], depth: 3,
    sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
    is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0, children: [contract],
  };
  const law = {
    id: '2', code: 'legal_law', name: '法律', aliases: [], parent_id: '1',
    path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2,
    sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
    is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0, children: [labor],
  };
  const inactiveArchive = {
    id: '8', code: 'inactive_archive', name: '已停用资料', aliases: ['旧资料'], parent_id: '1',
    path: ['法律法规', '已停用资料'], path_ids: ['1', '8'], depth: 2,
    sort_order: 20, assignable: true, sensitive: false, effective_sensitive: false,
    is_system: false, status: 'inactive', direct_document_count: 0, total_document_count: 0, children: [],
  };
  const legal = {
    id: '1', code: 'legal', name: '法律法规', aliases: [], parent_id: null,
    path: ['法律法规'], path_ids: ['1'], depth: 1, sort_order: 10,
    assignable: false, sensitive: false, effective_sensitive: false,
    is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0, children: [law, inactiveArchive],
  };
  await page.route('**/api/rag/categories**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: [legal] }),
  }));
  await page.route('**/api/rag/documents?**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 5 }),
  }));

  await page.goto('/knowledge/categories?category_id=1&doc_page=1');
  await expect(page.getByRole('tab', { name: /分类管理/ })).toHaveAttribute('aria-selected', 'true');
  const firstLevel = page.getByRole('region', { name: '一级分类' });
  const secondLevel = page.getByRole('region', { name: '二级分类' });
  await expect(firstLevel.getByText('法律法规', { exact: true })).toBeVisible();
  await expect(firstLevel.getByText('法律', { exact: true })).toHaveCount(0);
  await expect(secondLevel.getByText('法律', { exact: true })).toBeVisible();
  await expect(secondLevel.getByText('法律法规', { exact: true })).toHaveCount(0);
  await expect(secondLevel.getByText('已停用资料', { exact: true })).toHaveCount(0);
  const inactiveSection = page.getByRole('region', { name: '已停用分类' });
  await expect(inactiveSection.getByText('法律法规 / 已停用资料')).toBeVisible();
  await expect(inactiveSection.getByRole('button', { name: '重新启用' })).toBeVisible();

  await secondLevel.getByRole('button', { name: /^法律/ }).click();
  await page.getByRole('region', { name: '三级分类' }).getByRole('button', { name: /^劳动法律/ }).click();
  await expect(page.getByRole('region', { name: '四级分类' })).toContainText('劳动合同');
  await expect(page).toHaveURL(/category_id=3.*doc_page=1/);

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  expect(internalRequests).toEqual([]);
});

test('category management supports batch move and batch delete', async ({ page }) => {
  const internalRequests: string[] = [];
  const apiRequests: { url: string; method: string; body?: unknown }[] = [];
  page.on('request', (request) => {
    if (/:(8000|9000|19530)\b/.test(request.url())) internalRequests.push(request.url());
  });
  page.on('requestfinished', async (request) => {
    if (request.url().includes('/api/rag/documents/batch')) {
      apiRequests.push({
        url: request.url(),
        method: request.method(),
        body: request.postDataJSON(),
      });
    }
  });

  const legal = {
    id: '1', code: 'legal', name: '法律法规', aliases: [], parent_id: null,
    path: ['法律法规'], path_ids: ['1'], depth: 1, sort_order: 10,
    assignable: false, sensitive: false, effective_sensitive: false,
    is_system: false, status: 'active', direct_document_count: 2, total_document_count: 2,
    children: [{
      id: '2', code: 'legal_law', name: '法律', aliases: [], parent_id: '1',
      path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2,
      sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
      is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0, children: [],
    }],
  };
  const docs = [
    { doc_id: '10', attachment_id: '1', title: '文档一', category: '法律法规', category_id: '1', category_name: '法律法规', category_path: ['法律法规'], category_path_ids: ['1'], category_sensitive: false, embedding_status: 'success', file_name: 'a.md', file_size: '10', source_count: 1, image_total: 0, created_at: '2026-07-17T00:00:00Z', upload_timings: null, ingest_timings: null },
    { doc_id: '11', attachment_id: '2', title: '文档二', category: '法律法规', category_id: '1', category_name: '法律法规', category_path: ['法律法规'], category_path_ids: ['1'], category_sensitive: false, embedding_status: 'success', file_name: 'b.md', file_size: '10', source_count: 1, image_total: 0, created_at: '2026-07-17T00:00:00Z', upload_timings: null, ingest_timings: null },
  ];

  await page.route('**/api/rag/categories**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: [legal] }),
  }));
  await page.route('**/api/rag/documents?**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: docs, total: 2, page: 1, page_size: 5 }),
  }));
  await page.route('**/api/rag/documents/batch-move', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ moved: 2, category_id: '2', category_path: ['法律法规', '法律'] }),
  }));
  await page.route('**/api/rag/documents/batch-delete', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ deleted: 2, mode: 'soft', artifacts_retained: true }),
  }));

  await page.goto('/knowledge/categories?category_id=1&doc_page=1');
  await expect(page.getByText('文档一')).toBeVisible();
  await expect(page.getByText('文档二')).toBeVisible();

  const cards = page.locator('.category-document-card');
  await cards.first().locator('input[type="checkbox"]').check();
  await cards.nth(1).locator('input[type="checkbox"]').check();
  await expect(page.getByText('已选 2 份')).toBeVisible();

  await page.getByRole('button', { name: '批量移动' }).click();
  await page.getByLabel('目标一级分类').selectOption('1');
  await page.getByLabel('目标二级分类').selectOption('2');
  await page.getByRole('button', { name: '确认批量移动' }).click();
  await expect(page.getByText(/已批量移动 2 份文档/)).toBeVisible();

  await cards.first().locator('input[type="checkbox"]').check();
  await cards.nth(1).locator('input[type="checkbox"]').check();
  await page.getByRole('button', { name: '批量删除' }).click();
  await page.getByRole('button', { name: '确认删除' }).click();
  await expect(page.getByText(/已删除 2 份文档/)).toBeVisible();

  expect(apiRequests).toHaveLength(2);
  expect(apiRequests[0]).toMatchObject({
    url: expect.stringContaining('/api/rag/documents/batch-move'),
    method: 'POST',
    body: { doc_ids: ['10', '11'], category_id: '2' },
  });
  expect(apiRequests[1]).toMatchObject({
    url: expect.stringContaining('/api/rag/documents/batch-delete'),
    method: 'POST',
    body: { doc_ids: ['10', '11'] },
  });
  expect(internalRequests).toEqual([]);
});

test('recycle bin restores and purges behind the platform gateway', async ({ page }) => {
  const internalRequests: string[] = [];
  const apiRequests: { url: string; method: string; body?: unknown }[] = [];
  page.on('request', (request) => {
    if (/:(8000|9000|19530)\b/.test(request.url())) internalRequests.push(request.url());
  });
  page.on('requestfinished', async (request) => {
    if (request.url().includes('/api/rag/documents/batch-')) {
      apiRequests.push({
        url: request.url(),
        method: request.method(),
        body: request.postDataJSON(),
      });
    }
  });

  const legal = {
    id: '1', code: 'legal', name: '法律法规', aliases: [], parent_id: null,
    path: ['法律法规'], path_ids: ['1'], depth: 1, sort_order: 10,
    assignable: false, sensitive: false, effective_sensitive: false,
    is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0,
    children: [{
      id: '2', code: 'legal_law', name: '法律', aliases: [], parent_id: '1',
      path: ['法律法规', '法律'], path_ids: ['1', '2'], depth: 2,
      sort_order: 10, assignable: true, sensitive: false, effective_sensitive: false,
      is_system: false, status: 'active', direct_document_count: 0, total_document_count: 0, children: [],
    }],
  };
  const trashDoc = {
    doc_id: '40', attachment_id: '60', title: '已删除的法规',
    category_id: '2', category_name: '法律', category_path: ['法律法规', '法律'],
    category_path_ids: ['1', '2'], category_valid: true, restorable: true,
    deleted_at: '2026-07-19T03:30:00Z', embedding_status: 'success',
    file_name: 'old.md', file_size: '128', source_count: 1,
  };

  await page.route('**/api/rag/categories**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: [legal] }),
  }));
  await page.route('**/api/rag/documents/trash**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: [trashDoc], total: 1, page: 1, page_size: 10 }),
  }));
  await page.route('**/api/rag/documents/batch-restore', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ restored: 1, doc_ids: ['40'] }),
  }));
  await page.route('**/api/rag/documents/batch-purge', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ purged: 1, already_purged: 0 }),
  }));

  await page.goto('/knowledge/trash');
  await expect(page.getByRole('tab', { name: /回收站/ })).toHaveAttribute('aria-selected', 'true');
  // 顶部五个一级模块，顺序：法条检索 / 知识问答 / 知识库管理 / 分类管理 / 回收站。
  // 用 textContent 取完整导航文本。
  const labels = await page.getByRole('tab').evaluateAll((els) =>
    els.map((e) => e.textContent ?? ''),
  );
  expect(labels).toEqual([
    expect.stringContaining('法条检索'),
    expect.stringContaining('知识问答'),
    expect.stringContaining('知识库管理'),
    expect.stringContaining('分类管理'),
    expect.stringContaining('回收站'),
  ]);
  await expect(page.getByText('已删除的法规')).toBeVisible();

  await page.locator('.trash-row').locator('input[type="checkbox"]').check();
  await page.getByRole('button', { name: '批量恢复' }).click();
  await page.getByRole('button', { name: '确认恢复' }).click();
  await expect(page.getByText(/已恢复 1 份文档/)).toBeVisible();

  await page.locator('.trash-row').locator('input[type="checkbox"]').check();
  await page.getByRole('button', { name: '批量彻底删除' }).click();
  await expect(page.getByRole('button', { name: '确认彻底删除' })).toBeDisabled();
  await page.getByRole('checkbox', { name: '确认永久删除' }).check();
  await page.getByRole('button', { name: '确认彻底删除' }).click();
  await expect(page.getByText(/已彻底删除 1 份文档/)).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  expect(internalRequests).toEqual([]);
  expect(apiRequests).toEqual([
    { url: expect.stringContaining('/api/rag/documents/batch-restore'), method: 'POST', body: { doc_ids: ['40'] } },
    { url: expect.stringContaining('/api/rag/documents/batch-purge'), method: 'POST', body: { doc_ids: ['40'] } },
  ]);
});
