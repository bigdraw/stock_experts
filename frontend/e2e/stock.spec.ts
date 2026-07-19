import { test, expect } from '@playwright/test';

// 辅助函数：登录
async function login(page: any) {
  await page.goto('/login');
  await page.waitForSelector('input[placeholder="请输入用户名"]');
  await page.fill('input[placeholder="请输入用户名"]', 'e2etest');
  await page.fill('input[placeholder="请输入密码"]', 'e2etest123');
  await Promise.all([
    page.waitForURL('/', { timeout: 10000 }),
    page.click('button:has-text("登录")')
  ]);
  await expect(page).toHaveURL('/');
}

// 辅助函数：确保有组合且有股票
async function ensurePortfolioWithStocks(page: any) {
  await page.click('text=股票列表');
  await page.waitForURL('/stocks');
  
  // 检查是否有空状态
  const emptyState = page.locator('text=还没有自选股组合');
  const hasEmptyState = await emptyState.isVisible({ timeout: 3000 }).catch(() => false);
  
  if (hasEmptyState) {
    // 创建组合
    await page.click('button:has-text("创建自选组合")');
    await page.waitForSelector('.n-modal');
    await page.fill('input[placeholder="输入组合名称"]', '测试组合');
    await page.fill('textarea[placeholder="输入组合描述（可选）"]', 'E2E测试创建的组合');
    await page.click('.n-modal button:has-text("创建")');
    await page.waitForSelector('text=组合创建成功', { timeout: 5000 });
  }
  
  // 等待标签页加载
  await page.waitForSelector('.n-tabs-tab', { timeout: 5000 });
  
  // 等待表格出现
  await page.waitForSelector('.n-data-table', { timeout: 5000 });
  
  // 检查组合是否有股票
  let rowCount = await page.locator('tbody tr').count();
  
  if (rowCount === 0) {
    // 通过搜索添加股票
    await page.fill('input[placeholder*="搜索"]', '000001');
    await page.waitForTimeout(1500);
    
    // 等待下拉选项出现
    const firstOption = page.locator('.search-option-item').first();
    await expect(firstOption).toBeVisible({ timeout: 5000 });
    
    // 点击下拉选项中的"添加"按钮
    const addButton = firstOption.locator('button:has-text("添加")');
    await addButton.click();
    
    // 等待表格出现新行
    await page.waitForTimeout(2000);
    
    // 清空搜索
    await page.fill('input[placeholder*="搜索"]', '');
    await page.waitForTimeout(1000);
  }
}

test.describe('股票列表页面', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('侧边栏导航在股票详情页正常工作', async ({ page }) => {
    await ensurePortfolioWithStocks(page);
    
    // 点击第一个股票的"详情"按钮
    const firstStockButton = page.locator('tbody tr').first().locator('button:has-text("详情")');
    await firstStockButton.click();
    await page.waitForURL(/\/stocks\/\d{6}/);

    // 验证详情页加载
    await expect(page.locator('.page-header')).toBeVisible();

    // 测试侧边栏导航 - 投资组合
    await page.click('text=投资组合');
    await page.waitForURL('/portfolios');
    await expect(page.locator('h2:has-text("投资组合")')).toBeVisible();

    // 返回股票列表
    await page.click('text=股票列表');
    await page.waitForURL('/stocks');
    
    // 等待标签页加载
    await page.waitForSelector('.n-tabs-tab', { timeout: 5000 });
    
    // 等待数据加载（等待 loading 状态消失）
    await page.waitForTimeout(1000);
    
    // 等待表格出现（可能为空表格，但至少要有表格结构）
    await page.waitForSelector('.n-data-table', { timeout: 10000 });
    
    // 如果有数据，等待行出现
    const hasData = await page.locator('tbody tr').count() > 0;
    if (!hasData) {
      // 如果表格为空，等待一下看是否会加载
      await page.waitForTimeout(2000);
    }

    // 测试侧边栏导航 - 筛选工具库
    await page.click('text=筛选工具库');
    await page.waitForURL('/filters');
    await expect(page.locator('h2:has-text("筛选工具库")')).toBeVisible();

    // 测试侧边栏导航 - 策略回测
    await page.click('text=策略回测');
    await page.waitForURL('/backtest');
    await expect(page.locator('h2:has-text("策略回测")')).toBeVisible();
  });

  test('搜索框显示下拉候选列表，不影响下方表格', async ({ page }) => {
    await ensurePortfolioWithStocks(page);
    
    // 获取初始表格行数
    const initialRowCount = await page.locator('tbody tr').count();
    expect(initialRowCount).toBeGreaterThan(0);

    // 在搜索框输入
    await page.fill('input[placeholder*="搜索"]', '000001');
    
    // 等待防抖和 API 调用
    await page.waitForTimeout(1000);
    
    // 验证下拉候选列表出现
    await expect(page.locator('.search-option-item').first()).toBeVisible({ timeout: 5000 });
    
    // 验证下拉选项包含"详情"和"添加"按钮
    const firstOption = page.locator('.search-option-item').first();
    await expect(firstOption.locator('button:has-text("详情")')).toBeVisible();
    await expect(firstOption.locator('button:has-text("添加")')).toBeVisible();
    
    // 验证表格行数未变（搜索不影响表格）
    const currentRowCount = await page.locator('tbody tr').count();
    expect(currentRowCount).toBe(initialRowCount);

    // 清空搜索框
    await page.fill('input[placeholder*="搜索"]', '');
    await page.waitForTimeout(500);
    
    // 验证表格仍然不变
    const restoredRowCount = await page.locator('tbody tr').count();
    expect(restoredRowCount).toBe(initialRowCount);
  });

  test('通过搜索下拉添加股票到组合', async ({ page }) => {
    await ensurePortfolioWithStocks(page);
    
    // 获取初始表格行数
    const initialRowCount = await page.locator('tbody tr').count();

    // 搜索一个不在组合中的股票（使用 600000 系列，避免与 000001 重复）
    await page.fill('input[placeholder*="搜索"]', '600000');
    await page.waitForTimeout(1500);
    
    // 验证下拉候选列表出现
    const firstOption = page.locator('.search-option-item').first();
    await expect(firstOption).toBeVisible({ timeout: 5000 });
    
    // 点击"添加"按钮
    const addButton = firstOption.locator('button:has-text("添加")');
    await addButton.click();
    
    // 验证添加成功提示
    await page.waitForSelector('text=已添加', { timeout: 5000 });
    
    // 等待表格刷新
    await page.waitForTimeout(500);
    
    // 验证表格行数增加
    const newRowCount = await page.locator('tbody tr').count();
    expect(newRowCount).toBeGreaterThan(initialRowCount);
  });
});

test.describe('投资组合', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('创建组合并添加股票', async ({ page }) => {
    // 进入投资组合页面
    await page.click('text=投资组合');
    await page.waitForURL('/portfolios');

    // 创建新组合
    await page.click('button:has-text("创建组合")');
    await page.waitForSelector('.n-modal');
    
    await page.fill('input[placeholder="请输入组合名称"]', 'E2E测试组合');
    await page.fill('textarea[placeholder="请输入组合描述（可选）"]', 'E2E测试创建的组合');
    await page.click('.n-modal button:has-text("创建")');

    // 等待组合创建成功
    await page.waitForSelector('text=组合创建成功', { timeout: 5000 });

    // 进入新创建的组合
    const newPortfolio = page.locator('.n-card:has-text("E2E测试组合")').first();
    await newPortfolio.click();
    await page.waitForURL(/\/portfolios\/\d+/);

    // 添加股票
    await page.fill('input[placeholder="输入代码、名称、拼音或首字母"]', '000001');
    await page.click('button:has-text("添加股票")');

    // 验证股票添加成功
    await page.waitForSelector('text=已添加', { timeout: 5000 });
    await expect(page.locator('tbody')).toContainText('000001');
  });
});
