# UI 设计文档

> 参考：ChatGPT · 豆包 · Apple 主页
> 气质关键词：**干净 · 温馨 · 亲和**
> 不是冷冰冰的科技黑，而是让人愿意停留的暖色调。

---

## 1. 配色方案

### 深色模式（默认）

不使用纯黑 #000（太冷太硬）。参考 ChatGPT 的暖灰：

| 变量 | 值 | 用途 |
|------|-----|------|
| `--bg-base` | `#1a1a2e` | 页面底层（微蓝灰，非纯黑） |
| `--bg-elevated` | `#16213e` | 卡片/侧边栏 |
| `--bg-surface` | `#0f3460` | 输入框/按钮底 |
| `--bg-glass` | `rgba(26,26,46,0.85)` | 毛玻璃层 |

### 语义色（参考 Apple HIG 但偏暖）

| 变量 | 值 | 用途 |
|------|-----|------|
| `--primary` | `#e94560` | 主色——珊瑚红，温暖不刺眼 |
| `--primary-hover` | `#f05670` | hover |
| `--accent` | `#533483` | 辅助——深紫，品质感 |
| `--success` | `#0f9b8e` | 成功——薄荷绿 |
| `--warning` | `#f5a623` | 警告——琥珀 |
| `--error` | `#e74c3c` | 错误——砖红 |

### 文字

| 变量 | 值 |
|------|-----|
| `--text-primary` | `#f5f5f7` | Apple 白 |
| `--text-secondary` | `rgba(245,245,247,0.75)` |
| `--text-tertiary` | `rgba(245,245,247,0.45)` |

### 渐变（仅用于 Logo 文字，不用于按钮/边框）

`linear-gradient(135deg, #e94560, #533483)` — 珊瑚→深紫，温暖优雅。

---

## 2. 布局规范

### 间距

- 卡片内边距：`20px`
- 区块间距：`16px`
- 页面外边距：`24px`
- 按钮内边距：`10px 20px`

### 圆角

统一两档：
- 小（按钮/输入框/标签）：`10px`
- 大（卡片/面板/弹窗）：`14px`

**不要胶囊圆角（9999px）**——那是 Telegram 风格，不是我们要的。

### 边框

统一 `1px solid rgba(255,255,255,0.06)`——几乎看不见但有层次。

---

## 3. 动画规范

**原则：动画必须贴合容器边界。** 之前的错误是动画溢出了圆角边框。

- `transition: all 0.2s ease`——统一缓动
- hover 效果：仅 `background` 变化，不用 `transform: translateY`（会破坏布局对齐）
- 不用 `::before` 伪元素做扫光/边线（容易溢出 border-radius）
- 不用 `pulse`/`glow` 呼吸灯
- 卡片 hover：`border-color` 变亮即可

---

## 4. 字体

```css
font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'PingFang SC', sans-serif;
```

- 正文：`15px` / `line-height: 1.6`
- 标题：`22px` / `font-weight: 600`
- 小字：`13px` / `color: var(--text-tertiary)`

---

## 5. 组件风格

### 卡片
```
background: var(--bg-elevated);
border: 1px solid var(--border-subtle);
border-radius: 14px;
padding: 20px;
/* 无阴影，无 hover 变形，仅 border-color 微变 */
```

### 按钮
```
border-radius: 10px;
font-weight: 500;
transition: opacity 0.2s ease;  /* 用 opacity 不用 transform */
/* primary: background var(--primary) */
/* hover: opacity 0.85 */
```

### 输入框
```
background: var(--bg-surface);
border: 1px solid var(--border-subtle);
border-radius: 10px;
padding: 10px 16px;
/* focus: border-color var(--primary) + box-shadow 0 0 0 3px rgba(233,69,96,0.1) */
```

### 聊天气泡
```
/* user: background var(--primary), color #fff, border-radius 14px 14px 4px 14px */
/* assistant: background var(--bg-elevated), border-radius 14px 14px 14px 4px */
max-width: 75%;
padding: 12px 16px;
/* 无边框，无阴影，干净 */
```

### 侧边栏
```
background: var(--bg-elevated);
border-right: 1px solid var(--border-subtle);
/* 菜单项 hover: background var(--bg-surface), border-radius 10px, 无伪元素 */
```

---

## 6. 去掉的东西

- ❌ `gradient-text` 渐变文字（只在 Logo 处保留）
- ❌ `glow` / `pulse` 呼吸灯
- ❌ `::before` 扫光效果
- ❌ `transform: translateY` hover 变形
- ❌ 纯黑 #000 背景
- ❌ 胶囊圆角 9999px（改回 10px/14px）
- ❌ 斑马纹 `nth-child(even)`
- ❌ 菜单左侧竖线指示器

---

## 7. 实施清单

1. `style.css` — 全局重写（按上述配色+规范）
2. `ChatHome.vue` — 气泡+输入栏按规范
3. `AppLayout.vue` — 侧边栏+顶栏按规范
4. `Login.vue` — 登录页（如需要）
5. 其他页面的 `<style scoped>` 中引用旧变量的地方自动生效

**关键：改完后 vite build 通过 + 页面肉眼可见的"干净温馨"改善。**
