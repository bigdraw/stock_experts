<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" :theme="null" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { zhCN, dateZhCN } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

// 暖奶油 + 珊瑚 + 蜜糖 + 鼠尾草 — 小雷是股神主题
const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#FF6B5C',
    primaryColorHover: '#FF8275',
    primaryColorPressed: '#E85A4D',
    primaryColorSuppl: '#FF6B5C',
    infoColor: '#FFC857',
    infoColorHover: '#FFD67A',
    infoColorPressed: '#E5B44A',
    successColor: '#5BA882',
    successColorHover: '#6FBC97',
    successColorPressed: '#4A9472',
    warningColor: '#FFC857',
    errorColor: '#E74C3C',
    bodyColor: '#FBF7F0',
    cardColor: '#FFFFFF',
    modalColor: '#FFFFFF',
    popoverColor: '#FFFFFF',
    tableColor: '#FFFFFF',
    inputColor: '#FFFFFF',
    actionColor: '#FBF7F0',
    hoverColor: 'rgba(255, 107, 92, 0.08)',
    pressedColor: 'rgba(255, 107, 92, 0.12)',
    borderColor: 'rgba(45, 42, 38, 0.12)',
    dividerColor: 'rgba(45, 42, 38, 0.08)',
    textColorBase: '#2D2A26',
    textColor1: '#2D2A26',
    textColor2: 'rgba(45, 42, 38, 0.7)',
    textColor3: 'rgba(45, 42, 38, 0.45)',
    textColorDisabled: 'rgba(45, 42, 38, 0.25)',
    placeholderColor: 'rgba(45, 42, 38, 0.35)',
    fontFamily: '"Nunito", -apple-system, BlinkMacSystemFont, "PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei", "Segoe UI", sans-serif',
    borderRadius: '16px',
    borderRadiusSmall: '10px',
  },
  Button: {
    colorPrimary: '#FF6B5C',
    colorHoverPrimary: '#FF8275',
    colorPressedPrimary: '#E85A4D',
    borderPrimary: 'none',
    borderHoverPrimary: 'none',
    borderPressedPrimary: 'none',
    textColorPrimary: '#FFFFFF',
    fontWeight: '700',
    borderRadius: '10px',
  },
  Card: {
    color: '#FFFFFF',
    colorModal: '#FFFFFF',
    borderColor: 'rgba(45, 42, 38, 0.08)',
    borderRadius: '16px',
    paddingMedium: '20px',
  },
  Input: {
    color: '#FFFFFF',
    colorFocus: '#FFFFFF',
    border: '1px solid rgba(45, 42, 38, 0.12)',
    borderHover: '1px solid rgba(255, 107, 92, 0.4)',
    borderFocus: '1px solid #FF6B5C',
    boxShadowFocus: '0 0 0 3px rgba(255, 107, 92, 0.12)',
    borderRadius: '10px',
  },
  DataTable: {
    thColor: '#FBF7F0',
    tdColor: '#FFFFFF',
    tdColorHover: 'rgba(255, 107, 92, 0.05)',
    borderColor: 'rgba(45, 42, 38, 0.08)',
    borderRadius: '16px',
    thTextColor: 'rgba(45, 42, 38, 0.45)',
    tdTextColor: '#2D2A26',
  },
  Menu: {
    color: 'transparent',
    itemColorHover: 'rgba(255, 107, 92, 0.06)',
    itemColorActive: 'rgba(255, 107, 92, 0.10)',
    itemColorActiveHover: 'rgba(255, 107, 92, 0.14)',
    itemTextColor: 'rgba(45, 42, 38, 0.7)',
    itemTextColorHover: '#FF6B5C',
    itemTextColorActive: '#FF6B5C',
    itemIconColor: 'rgba(45, 42, 38, 0.45)',
    itemIconColorHover: '#FF6B5C',
    itemIconColorActive: '#FF6B5C',
    borderRadius: '10px',
  },
  Tag: {
    borderRadius: '8px',
  },
  Statistic: {
    labelTextColor: 'rgba(45, 42, 38, 0.45)',
    valueTextColor: '#2D2A26',
  },
}
</script>
