<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { zhCN, dateZhCN, darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#00d4aa',
    primaryColorHover: '#00f4c4',
    primaryColorPressed: '#00b490',
    primaryColorSuppl: '#00d4aa',
    infoColor: '#6366f1',
    infoColorHover: '#818cf8',
    infoColorPressed: '#4f46e5',
    successColor: '#10b981',
    warningColor: '#f59e0b',
    errorColor: '#ef4444',
    bodyColor: '#0a0e1a',
    cardColor: 'rgba(15, 23, 42, 0.8)',
    modalColor: 'rgba(15, 23, 42, 0.95)',
    popoverColor: 'rgba(15, 23, 42, 0.95)',
    tableColor: 'rgba(15, 23, 42, 0.6)',
    inputColor: 'rgba(30, 41, 59, 0.8)',
    actionColor: 'rgba(30, 41, 59, 0.6)',
    hoverColor: 'rgba(0, 212, 170, 0.1)',
    pressedColor: 'rgba(0, 212, 170, 0.15)',
    borderColor: 'rgba(100, 116, 139, 0.3)',
    dividerColor: 'rgba(100, 116, 139, 0.2)',
    textColorBase: '#e2e8f0',
    textColor1: '#f1f5f9',
    textColor2: '#cbd5e1',
    textColor3: '#94a3b8',
    textColorDisabled: '#475569',
    placeholderColor: '#64748b',
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    borderRadius: '8px',
    borderRadiusSmall: '6px',
  },
  Button: {
    colorPrimary: 'linear-gradient(135deg, #00d4aa 0%, #6366f1 100%)',
    colorHoverPrimary: 'linear-gradient(135deg, #00f4c4 0%, #818cf8 100%)',
    colorPressedPrimary: 'linear-gradient(135deg, #00b490 0%, #4f46e5 100%)',
    borderPrimary: 'none',
    borderHoverPrimary: 'none',
    borderPressedPrimary: 'none',
    textColorPrimary: '#ffffff',
    fontWeight: '600',
  },
  Card: {
    color: 'rgba(15, 23, 42, 0.8)',
    borderColor: 'rgba(100, 116, 139, 0.2)',
    borderRadius: '12px',
    paddingMedium: '20px',
  },
  Input: {
    color: 'rgba(30, 41, 59, 0.8)',
    colorFocus: 'rgba(30, 41, 59, 1)',
    border: '1px solid rgba(100, 116, 139, 0.3)',
    borderHover: '1px solid rgba(0, 212, 170, 0.5)',
    borderFocus: '1px solid #00d4aa',
    boxShadowFocus: '0 0 0 2px rgba(0, 212, 170, 0.2)',
    borderRadius: '8px',
  },
  DataTable: {
    thColor: 'rgba(30, 41, 59, 0.8)',
    tdColor: 'rgba(15, 23, 42, 0.6)',
    tdColorHover: 'rgba(0, 212, 170, 0.08)',
    borderColor: 'rgba(100, 116, 139, 0.15)',
    borderRadius: '8px',
    thTextColor: '#e2e8f0',
    tdTextColor: '#cbd5e1',
  },
  Menu: {
    color: 'transparent',
    itemColorHover: 'rgba(0, 212, 170, 0.1)',
    itemColorActive: 'rgba(0, 212, 170, 0.15)',
    itemColorActiveHover: 'rgba(0, 212, 170, 0.2)',
    itemTextColor: '#94a3b8',
    itemTextColorHover: '#e2e8f0',
    itemTextColorActive: '#00d4aa',
    itemIconColor: '#64748b',
    itemIconColorHover: '#00d4aa',
    itemIconColorActive: '#00d4aa',
    borderRadius: '8px',
  },
  Tag: {
    borderRadius: '6px',
  },
  Statistic: {
    labelTextColor: '#94a3b8',
    valueTextColor: '#f1f5f9',
  },
}
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #0a0e1a;
  color: #e2e8f0;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* 自定义滚动条 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: rgba(15, 23, 42, 0.5);
}

::-webkit-scrollbar-thumb {
  background: rgba(100, 116, 139, 0.5);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(100, 116, 139, 0.7);
}

/* 全局发光效果 */
.glow-primary {
  box-shadow: 0 0 20px rgba(0, 212, 170, 0.3);
}

.glow-info {
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.3);
}

/* 渐变文字 */
.gradient-text {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* 毛玻璃效果 */
.glass {
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

/* 动画 */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.fade-in {
  animation: fadeIn 0.3s ease-out;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>
