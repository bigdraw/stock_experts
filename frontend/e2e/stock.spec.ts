import { test, expect } from '@playwright/test';

test.describe('股票详情页', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('/login');
    
    // 等待登录页面加载完成
    await page.waitForSelector('input[placeholder="请输入用户名"]');
    
    // 填写登录表单
    await page.fill('input[placeholder="请输入用户名"]', 'e2etest');
    await page.fill('input[placeholder="请输入密码"]', 'e2etest123');
    
    // 点击登录按钮并等待导航
    await Promise.all([
      page.waitForURL('/', { timeout: 10000 }),
      page.click('button:has-text("登录")')
    ]);
    
    // 验证登录成功
    await expect(page).toHaveURL('/');
  });

  test('侧边栏导航在股票详情页正常工作', async ({ page }) => {
    // 进入股票列表
    await page.click('text=股票列表');
    await page.waitForURL('/stocks');
    
    // 等待表格加载
    await page.waitForSelector('tbody tr', { timeout: 5000 });

    // 点击第一个股票的"查看详情"按钮进入详情页
    const firstStockButton = page.locator('tbody tr').first().locator('button:has-text("查看详情")');
    await firstStockButton.click();
    await page.waitForURL(/\/stocks\/\d{6}/);

    // 验证股票详情页加载成功
    await expect(page.locator('.page-header')).toBeVisible();

    // 测试侧边栏导航 - 点击投资组合
    await page.click('text=投资组合');
    await page.waitForURL('/portfolios');
    await expect(page.locator('h2:has-text("投资组合")')).toBeVisible();

    // 再次进入股票详情
    await page.click('text=股票列表');
    await page.waitForURL('/stocks');
    await page.waitForSelector('tbody tr', { timeout: 5000 });
    const secondStockButton = page.locator('tbody tr').first().locator('button:has-text("查看详情")');
    await secondStockButton.click();
    await page.waitForURL(/\/stocks\/\d{6}/);

    // 测试侧边栏导航 - 点击筛选工具库
    await page.click('text=筛选工具库');
    await page.waitForURL('/filters');
    await expect(page.locator('h2:has-text("筛选工具库")')).toBeVisible();

    // 再次进入股票详情
    await page.click('text=股票列表');
    await page.waitForURL('/stocks');
    await page.waitForSelector('tbody tr', { timeout: 5000 });
    const thirdStockButton = page.locator('tbody tr').first().locator('button:has-text("查看详情")');
    await thirdStockButton.click();
    await page.waitForURL(/\/stocks\/\d{6}/);

    // 测试侧边栏导航 - 点击策略回测
    await page.click('text=策略回测');
    await page.waitForURL('/backtest');
    await expect(page.locator('h2:has-text("策略回测")')).toBeVisible();
  });

  test('股票列表搜索实时更新表格', async ({ page }) => {
    // 进入股票列表
    await page.click('text=股票列表');
    await page.waitForURL('/stocks');
    await page.waitForSelector('tbody tr', { timeout: 5000 });

    // 获取初始表格行数
    const initialRowCount = await page.locator('tbody tr').count();
    expect(initialRowCount).toBeGreaterThan(0);

    // 在搜索框输入
    await page.fill('input[placeholder*="搜索"]', '000001');
    
    // 等待防抖和 API 调用
    await page.waitForTimeout(1000);
    
    // 验证表格已更新（应该包含搜索的股票）
    await expect(page.locator('tbody')).toContainText('000001');
    
    // 验证搜索结果行数合理（最多100条，但由于分页可能只显示部分）
    const filteredRowCount = await page.locator('tbody tr').count();
    expect(filteredRowCount).toBeGreaterThan(0);
    expect(filteredRowCount).toBeLessThanOrEqual(100);

    // 清空搜索框
    await page.fill('input[placeholder*="搜索"]', '');
    await page.waitForTimeout(500);
    
    // 验证表格恢复到初始状态
    const restoredRowCount = await page.locator('tbody tr').count();
    expect(restoredRowCount).toBe(initialRowCount);
  });
});

test.describe('投资组合', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('/login');
    
    // 等待登录页面加载完成
    await page.waitForSelector('input[placeholder="请输入用户名"]');
    
    // 填写登录表单
    await page.fill('input[placeholder="请输入用户名"]', 'e2etest');
    await page.fill('input[placeholder="请输入密码"]', 'e2etest123');
    
    // 点击登录按钮并等待导航
    await Promise.all([
      page.waitForURL('/', { timeout: 10000 }),
      page.click('button:has-text("登录")')
    ]);
    
    // 验证登录成功
    await expect(page).toHaveURL('/');
  });

  test('创建组合并添加股票', async ({ page }) => {
    // 进入投资组合页面
    await page.click('text=投资组合');
    await page.waitForURL('/portfolios');

    // 创建新组合
    await page.click('button:has-text("创建组合")');
    await page.waitForSelector('.n-modal');
    
    await page.fill('input[placeholder="请输入组合名称"]', '测试组合');
    await page.fill('textarea[placeholder="请输入组合描述（可选）"]', 'E2E测试创建的组合');
    await page.click('.n-modal button:has-text("创建")');

    // 等待组合创建成功
    await page.waitForSelector('text=组合创建成功', { timeout: 5000 });

    // 进入新创建的组合
    const newPortfolio = page.locator('.n-card:has-text("测试组合")').first();
    await newPortfolio.click();
    await page.waitForURL(/\/portfolios\/\d+/);

    // 添加股票 - 输入股票代码
    await page.fill('input[placeholder="输入代码、名称、拼音或首字母"]', '000001');
    await page.click('button:has-text("添加股票")');

    // 验证股票添加成功
    await page.waitForSelector('text=已添加', { timeout: 5000 });
    await expect(page.locator('tbody')).toContainText('000001');
  });
});
