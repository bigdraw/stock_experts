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

test.describe('Dashboard 仪表盘', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('仪表盘页面正常加载', async ({ page }) => {
    await expect(page.locator('text=股票总数')).toBeVisible();
    await expect(page.locator('.stat-label:has-text("投资组合")')).toBeVisible();
    await expect(page.locator('text=筛选脚本')).toBeVisible();
    await expect(page.locator('text=投资Agent')).toBeVisible();
  });

  test('快速操作按钮正常工作', async ({ page }) => {
    await page.click('text=查看股票');
    await page.waitForURL('/stocks');
    await expect(page).toHaveURL('/stocks');
  });

  test('数据采集按钮正常显示', async ({ page }) => {
    await expect(page.locator('text=全量采集基础指标')).toBeVisible();
    await expect(page.locator('text=增量更新')).toBeVisible();
    await expect(page.locator('text=全量更新财务数据')).toBeVisible();
  });
});

test.describe('Backtest 回测', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('回测页面正常加载', async ({ page }) => {
    await page.click('text=策略回测');
    await page.waitForURL('/backtest');
    await expect(page.locator('text=创建策略')).toBeVisible();
    await expect(page.locator('input[placeholder="例：均线交叉策略"]')).toBeVisible();
  });

  test('可以输入策略描述', async ({ page }) => {
    await page.click('text=策略回测');
    await page.waitForURL('/backtest');
    
    await page.fill('input[placeholder="例：均线交叉策略"]', '测试策略');
    await page.fill('textarea[placeholder="例：均线交叉策略，5日均线上穿20日均线买入，下穿卖出"]', 
      '当5日均线上穿20日均线时买入，下穿时卖出');
    
    await expect(page.locator('input[placeholder="例：均线交叉策略"]')).toHaveValue('测试策略');
  });
});

test.describe('Debate 辩论', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('辩论页面正常加载', async ({ page }) => {
    await page.click('text=辩论分析');
    await page.waitForURL('/debate');
    await expect(page.locator('text=发起辩论')).toBeVisible();
    await expect(page.locator('text=选择 Agent（至少2个）')).toBeVisible();
  });

  test('可以输入股票代码', async ({ page }) => {
    await page.click('text=辩论分析');
    await page.waitForURL('/debate');
    
    await page.fill('input[placeholder="股票代码，如 600519"]', '000001');
    await expect(page.locator('input[placeholder="股票代码，如 600519"]')).toHaveValue('000001');
  });
});

test.describe('BookManager 书籍管理', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('书籍管理页面正常加载', async ({ page }) => {
    await page.click('text=书籍管理');
    await page.waitForURL('/books');
    await expect(page.locator('text=上传书籍')).toBeVisible();
    await expect(page.locator('text=选择文件 (PDF/EPUB/TXT)')).toBeVisible();
  });

  test('已有 Agent 列表正常显示', async ({ page }) => {
    await page.click('text=书籍管理');
    await page.waitForURL('/books');
    await expect(page.locator('text=已有 Agent')).toBeVisible();
  });
});

test.describe('Settings 设置', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('设置页面正常加载', async ({ page }) => {
    await page.click('text=系统设置');
    await page.waitForURL('/settings');
    await expect(page.locator('text=系统设置')).toBeVisible();
    await expect(page.locator('text=网络设置')).toBeVisible();
    await expect(page.locator('text=LLM 配置')).toBeVisible();
    await expect(page.locator('text=数据源配置')).toBeVisible();
    await expect(page.locator('text=回测摩擦成本')).toBeVisible();
  });

  test('可以切换代理设置', async ({ page }) => {
    await page.click('text=系统设置');
    await page.waitForURL('/settings');
    
    // 点击代理开关
    const proxySwitch = page.locator('.n-switch').first();
    await proxySwitch.click();
    
    // 等待设置保存
    await page.waitForTimeout(1000);
    await expect(page.locator('text=代理设置已更新')).toBeVisible();
  });
});

test.describe('AlertManager 告警管理', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('告警管理页面正常加载', async ({ page }) => {
    await page.click('text=告警管理');
    await page.waitForURL('/alerts');
    await expect(page.locator('.page-title:has-text("告警管理")')).toBeVisible();
    await expect(page.locator('input[placeholder="例：ROE告警"]')).toBeVisible();
  });

  test('可以创建告警', async ({ page }) => {
    await page.click('text=告警管理');
    await page.waitForURL('/alerts');
    
    await page.fill('input[placeholder="例：ROE告警"]', '测试告警');
    await page.fill('input[placeholder="例：ROE大于20%"]', 'ROE大于15%');
    
    await page.click('button:has-text("创建告警")');
    await page.waitForTimeout(2000);
    // 验证告警已创建（检查列表中是否包含新创建的告警）
    await expect(page.locator('.n-data-table')).toContainText('测试告警');
  });
});

test.describe('AdminUsers 管理员用户管理', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test.skip('管理员用户管理页面正常加载', async ({ page }) => {
    // 跳过此测试，因为需要管理员权限
    // 直接导航到管理员页面（因为菜单项只对 admin 用户显示）
    await page.goto('/admin/users');
    await page.waitForURL('/admin/users');
    await expect(page.locator('h1:has-text("用户管理")')).toBeVisible();
    await expect(page.locator('text=用户名')).toBeVisible();
  });
});
