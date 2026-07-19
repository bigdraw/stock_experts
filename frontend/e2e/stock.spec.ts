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

  test('股票详情页之间导航正常切换', async ({ page }) => {
    // 进入股票列表
    await page.click('text=股票列表');
    await page.waitForURL('/stocks');
    await page.waitForSelector('tbody tr', { timeout: 5000 });

    // 获取前两个股票的"查看详情"按钮
    const stocks = page.locator('tbody tr');
    const firstStockButton = stocks.nth(0).locator('button:has-text("查看详情")');
    const secondStockButton = stocks.nth(1).locator('button:has-text("查看详情")');

    // 进入第一个股票详情
    await firstStockButton.click();
    await page.waitForURL(/\/stocks\/\d{6}/);
    const firstUrl = page.url();
    const firstStockCode = firstUrl.match(/\/stocks\/(\d{6})/)?.[1];

    // 返回列表
    await page.click('text=股票列表');
    await page.waitForURL('/stocks');
    await page.waitForSelector('tbody tr', { timeout: 5000 });

    // 进入第二个股票详情
    const secondStockButtonAfterReturn = page.locator('tbody tr').nth(1).locator('button:has-text("查看详情")');
    await secondStockButtonAfterReturn.click();
    await page.waitForURL(/\/stocks\/\d{6}/);
    const secondUrl = page.url();
    const secondStockCode = secondUrl.match(/\/stocks\/(\d{6})/)?.[1];

    // 验证 URL 不同
    expect(firstStockCode).not.toBe(secondStockCode);

    // 验证页面内容已更新（股票代码显示在页面上）
    await expect(page.locator(`text=${secondStockCode}`)).toBeVisible();
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
    await page.fill('input[placeholder="股票代码"]', '000001');
    await page.click('button:has-text("添加股票")');

    // 验证股票添加成功
    await page.waitForSelector('text=已添加', { timeout: 5000 });
    await expect(page.locator('tbody')).toContainText('000001');
  });
});
