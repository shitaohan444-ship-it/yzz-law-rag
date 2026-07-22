import { expect, test } from '@playwright/test';
import { resolve } from 'node:path';

test.describe('真实 RAG 验收', () => {
  test.skip(process.env.REAL_RAG_E2E !== '1', '设置 REAL_RAG_E2E=1 后运行真实模型验收');
  test.describe.configure({ timeout: 240_000 });

  test('劳动合同法检索命中第二十条', async ({ page }) => {
    await page.goto('/');
    await page.getByLabel('检索问题').fill('试用期工资最低不能少于多少');
    await page.getByRole('button', { name: '开始检索' }).click();
    await expect(page.getByText(/劳动合同法/).first()).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText('第二十条').first()).toBeVisible();
  });

  test('产品缺陷问答返回民法典引用', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: /知识问答/ }).click();
    await page.getByLabel('法律问题').fill('产品缺陷造成损害生产厂家要赔吗');
    await page.getByRole('button', { name: '提交问题' }).click();
    await expect(
      page.getByRole('heading', { name: '知识库回答', exact: true }),
    ).toBeVisible({ timeout: 180_000 });
    await expect(page.getByText(/第一千二百零二条/).first()).toBeVisible();
    await expect(page.getByText('知识库依据不足')).toHaveCount(0);
  });

  test('无依据问题不展示伪造引用', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: /知识问答/ }).click();
    await page.getByLabel('法律问题').fill('盗窃数额较大的刑事量刑标准是什么');
    await page.getByRole('button', { name: '提交问题' }).click();
    await expect(page.getByText('知识库依据不足')).toBeVisible({ timeout: 180_000 });
    await expect(page.getByLabel('引用依据')).toHaveCount(0);
  });

  test('独立分类管理逐级显示真实分类树', async ({ page }) => {
    const internalRequests: string[] = [];
    page.on('request', (request) => {
      if (/:(8000|9000|19530)\b/.test(request.url())) internalRequests.push(request.url());
    });
    await page.goto('/knowledge/categories');
    await expect(page.getByRole('tab', { name: /分类管理/ })).toHaveAttribute('aria-selected', 'true');
    const firstLevel = page.getByRole('region', { name: '一级分类' });
    const secondLevel = page.getByRole('region', { name: '二级分类' });
    await expect(firstLevel.getByText('法律法规', { exact: true })).toBeVisible();
    await expect(firstLevel.getByText('法律', { exact: true })).toHaveCount(0);
    await expect(secondLevel.getByText('法律', { exact: true })).toBeVisible();
    await secondLevel.getByRole('button', { name: /^法律/ }).click();
    await page.getByRole('region', { name: '三级分类' }).getByRole('button', { name: /^劳动法律/ }).click();
    await expect(page.getByRole('region', { name: '四级分类' })).toContainText('劳动合同');
    await expect(page).toHaveURL(/category_id=\d+.*doc_page=1/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
    await page.getByRole('tab', { name: /知识库管理/ }).click();
    await expect(page.getByLabel('上传一级分类')).toBeVisible();
    await expect(page.getByLabel('上传二级分类')).toBeVisible();
    await expect(page.getByRole('button', { name: '分类管理' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '修改分类' })).toHaveCount(0);
    expect(internalRequests).toEqual([]);
  });

  test('真实上传工作资料、自动入库并识别重复文件', async ({ page }) => {
    test.setTimeout(1_000_000);
    const sourceFile = resolve('..', 'test_files', '工作资料', '律师实务笔记.md');

    await page.goto('/');
    await page.getByRole('tab', { name: /知识库管理/ }).click();
    await page.getByLabel('选择文件').setInputFiles(sourceFile);
    await page.getByLabel('文档标题').fill('公共知识库真实上传验收');
    await page.getByLabel('上传一级分类').selectOption({ label: '律所工作资料（不可直接归档）' });
    await page.getByLabel('上传二级分类').selectOption({ label: '技术部' });
    await page.getByRole('button', { name: '新建并自动入库' }).click();

    await expect(page.getByText(/已入库，共 \d+ 个片段|该文件已存在/)).toBeVisible({
      timeout: 950_000,
    });
    const row = page.locator('.document-card').filter({ hasText: '公共知识库真实上传验收' });
    await expect(row).toBeVisible();
    await expect(row.getByText('入库成功')).toBeVisible();
    const markdownPopupPromise = page.waitForEvent('popup');
    await row.getByRole('link', { name: '查看 Markdown' }).click();
    const markdownPopup = await markdownPopupPromise;
    await expect(markdownPopup.getByRole('heading', { name: '公共知识库真实上传验收' }).first()).toBeVisible();
    await expect(markdownPopup.getByText(/诉讼时效期间为三年/).first()).toBeVisible();
    await markdownPopup.close();

    await page.getByLabel('选择文件').setInputFiles(sourceFile);
    await page.getByLabel('文档标题').fill('重复标题不应创建新文档');
    await page.getByRole('button', { name: '新建并自动入库' }).click();
    await expect(page.getByText(/该文件已存在，已复用《公共知识库真实上传验收》/)).toBeVisible();
  });

  test('文档 30 可查看真实 Chunk 与最近入库耗时', async ({ page }) => {
    const internalRequests: string[] = [];
    page.on('request', (request) => {
      if (/:(8000|9000|19530)\b/.test(request.url())) {
        internalRequests.push(request.url());
      }
    });

    await page.goto('/');
    await page.getByRole('tab', { name: /知识库管理/ }).click();
    await page.getByLabel('按标题筛选').fill('腾某科技公司诉国家知识产权局');
    await page.getByRole('button', { name: '筛选' }).click();
    const row = page
      .locator('.document-card')
      .filter({ hasText: '腾某科技公司诉国家知识产权局等发明专利权无效行政纠纷案' });
    await expect(row).toBeVisible();
    await row.getByText('处理耗时').click();
    await expect(row.getByText('RAG 入库')).toBeVisible();
    await expect(row.getByText('已跳过')).toBeVisible();
    const chunkPopupPromise = page.waitForEvent('popup');
    await row.getByRole('link', { name: '查看 Chunk' }).click();
    const chunkPopup = await chunkPopupPromise;
    await expect(chunkPopup.getByText('30:m:0000')).toBeVisible();
    await expect(chunkPopup.getByText('30:m:0009')).toBeVisible();
    await expect(chunkPopup.getByText(/共 10 个 Chunk/)).toBeVisible();
    await chunkPopup.close();
    expect(internalRequests).toEqual([]);
  });

  test('安全替换验收文档通过源文件管理保留编号', async ({ page }) => {
    const internalRequests: string[] = [];
    page.on('request', (request) => {
      if (/:(8000|9000|19530)\b/.test(request.url())) internalRequests.push(request.url());
    });
    await page.goto('/');
    await page.getByRole('tab', { name: /知识库管理/ }).click();
    await page.getByLabel('按标题筛选').fill('知识库安全替换验收 V2');
    await page.getByRole('button', { name: '筛选' }).click();
    const row = page
      .locator('.document-card')
      .filter({ hasText: '知识库安全替换验收 V2（已替换）' });
    await expect(row).toBeVisible();
    await expect(row).toContainText('文档 #34');
    await expect(row).toContainText('案例');
    await expect(row).toContainText('知识库安全替换验收_V2.md');
    await row.getByRole('button', { name: '管理文件' }).click();
    const sourceCard = page.locator('.source-file-card').filter({
      hasText: '知识库安全替换验收_V2.md',
    });
    await expect(sourceCard).toBeVisible();
    await expect(sourceCard.getByText('主文件')).toBeVisible();
    await sourceCard.getByRole('button', { name: '替换文件' }).click();
    await expect(page.getByLabel('替换来源标题')).toHaveValue(
      '知识库安全替换验收_V2.md',
    );
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);
    expect(internalRequests).toEqual([]);
  });

  test('文档 38 的多源文件可管理并按来源查看 Chunk', async ({ page }) => {
    const internalRequests: string[] = [];
    page.on('request', (request) => {
      if (/:(8000|9000|19530)\b/.test(request.url())) internalRequests.push(request.url());
    });
    await page.goto('/');
    await page.getByRole('tab', { name: /知识库管理/ }).click();
    await expect(page.locator('.document-card')).toHaveCount(5);
    const largePageResponse = page.waitForResponse((response) =>
      response.url().includes('/api/rag/documents?') &&
      response.url().includes('page_size=1000'),
    );
    await page.getByLabel('已登记文档每页数量').selectOption('1000');
    await expect((await largePageResponse).status()).toBe(200);
    await expect(page.getByLabel('已登记文档每页数量')).toHaveValue('1000');
    await page.getByLabel('按标题筛选').fill('公共知识库多源追加真实验收');
    await page.getByRole('button', { name: '筛选' }).click();
    const row = page.locator('.document-card').filter({
      hasText: '公共知识库多源追加真实验收',
    });
    await expect(row).toBeVisible();
    await expect(row).toContainText('文档 #38');
    await expect(row).toContainText('2 个源文件');

    const markdownPopupPromise = page.waitForEvent('popup');
    await row.getByRole('link', { name: '查看 Markdown' }).click();
    const markdownPopup = await markdownPopupPromise;
    await expect(markdownPopup).toHaveURL(/\/knowledge\/documents\/38\/markdown$/);
    await expect(markdownPopup.getByText(/2 个来源/)).toBeVisible();
    await expect(markdownPopup.getByText(/CANGWU-PRIMARY-716/).first()).toBeVisible();
    await expect(markdownPopup.getByText(/CHIXIA-REPLACE-716/).first()).toBeVisible();
    await markdownPopup.close();

    const allChunksPopupPromise = page.waitForEvent('popup');
    await row.getByRole('link', { name: '查看 Chunk' }).click();
    const allChunksPopup = await allChunksPopupPromise;
    await expect(allChunksPopup).toHaveURL(/\/knowledge\/documents\/38\/chunks$/);
    await expect(allChunksPopup.getByText(/共 6 个 Chunk/)).toBeVisible();
    await expect(allChunksPopup.getByText('38:s:35:m:0000')).toBeVisible();
    await expect(allChunksPopup.getByText('38:s:36:m:0002')).toBeVisible();
    await allChunksPopup.close();

    await row.getByRole('button', { name: '管理文件' }).click();
    const sourceCards = page.locator('.source-file-card');
    await expect(sourceCards).toHaveCount(2);
    await expect(sourceCards.filter({ hasText: 'multi_source_primary.md' })).toContainText('主文件');
    const primary = sourceCards.filter({ hasText: 'multi_source_primary.md' });
    const primaryPopupPromise = page.waitForEvent('popup');
    await primary.getByRole('link', { name: '查看 Chunk' }).click();
    const primaryPopup = await primaryPopupPromise;
    await expect(primaryPopup.getByLabel('Chunk 来源筛选')).toHaveValue('35');
    await expect(primaryPopup.getByText(/共 3 个 Chunk/)).toBeVisible();
    await primaryPopup.close();

    const revised = sourceCards.filter({ hasText: '后续补充材料修订版' });
    await expect(revised).toBeVisible();
    const revisedPopupPromise = page.waitForEvent('popup');
    await revised.getByRole('link', { name: '查看 Chunk' }).click();
    const revisedPopup = await revisedPopupPromise;
    await expect(revisedPopup.getByLabel('Chunk 来源筛选')).toHaveValue('36');
    await expect(revisedPopup.getByText(/共 3 个 Chunk/)).toBeVisible();
    await expect(revisedPopup.getByText('38:s:36:m:0000')).toBeVisible();
    expect(await revisedPopup.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
    await revisedPopup.close();
    await expect(page.getByRole('dialog', { name: /管理《公共知识库多源追加真实验收》的源文件/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
    expect(internalRequests).toEqual([]);
  });
});
