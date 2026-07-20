/* 轻量 i18n（无 vue-i18n 依赖，reactive locale + t() 函数）。
   用法：import { t, locale, setLocale } from '@/i18n'
   模板里用 {{ t('nav.stocks') }} */
import { ref } from 'vue'

export type Lang = 'zh' | 'en' | 'ja' | 'ko'

const dict: Record<Lang, Record<string, string>> = {
  zh: {
    'nav.chat': '对话',
    'nav.dashboard': '仪表盘',
    'nav.stocks': '股票列表',
    'nav.portfolios': '投资组合',
    'nav.filters': '筛选工具库',
    'nav.backtest': '策略回测',
    'nav.debate': '辩论分析',
    'nav.agents': 'Agent构建',
    'nav.alerts': '告警管理',
    'nav.settings': '系统设置',
    'nav.users': '用户管理',
    'app.title': '股票分析',
    'app.subtitle': '智能投资平台',
    'chat.title': '投资分析对话',
    'chat.placeholder': '输入问题…  / 列技能  @ 指定 Agent',
    'chat.send': '发送',
    'chat.hint': '输入问题或分析请求 · / 列技能 · @ 指定 Agent',
    'common.loading': '加载中…',
    'common.delete': '删除',
    'common.cancel': '取消',
    'common.save': '保存',
  },
  en: {
    'nav.chat': 'Chat',
    'nav.dashboard': 'Dashboard',
    'nav.stocks': 'Stocks',
    'nav.portfolios': 'Portfolios',
    'nav.filters': 'Filters',
    'nav.backtest': 'Backtest',
    'nav.debate': 'Debate',
    'nav.agents': 'Agent Builder',
    'nav.alerts': 'Alerts',
    'nav.settings': 'Settings',
    'nav.users': 'Users',
    'app.title': 'Stock Analysis',
    'app.subtitle': 'AI Investment Platform',
    'chat.title': 'Investment Analysis Chat',
    'chat.placeholder': 'Ask…  / list skills  @ mention Agent',
    'chat.send': 'Send',
    'chat.hint': 'Type a question · / for skills · @ to mention Agent',
    'common.loading': 'Loading…',
    'common.delete': 'Delete',
    'common.cancel': 'Cancel',
    'common.save': 'Save',
  },
  ja: {
    'nav.chat': 'チャット',
    'nav.dashboard': 'ダッシュボード',
    'nav.stocks': '銘柄一覧',
    'nav.portfolios': 'ポートフォリオ',
    'nav.filters': 'フィルター',
    'nav.backtest': 'バックテスト',
    'nav.debate': 'ディベート',
    'nav.agents': 'エージェント構築',
    'nav.alerts': 'アラート',
    'nav.settings': '設定',
    'nav.users': 'ユーザー',
    'app.title': '株式分析',
    'app.subtitle': 'AI投資プラットフォーム',
    'chat.title': '投資分析チャット',
    'chat.placeholder': '質問を入力…  / スキル  @ エージェント',
    'chat.send': '送信',
    'chat.hint': '質問を入力 · / スキル一覧 · @ エージェント指定',
    'common.loading': '読み込み中…',
    'common.delete': '削除',
    'common.cancel': 'キャンセル',
    'common.save': '保存',
  },
  ko: {
    'nav.chat': '채팅',
    'nav.dashboard': '대시보드',
    'nav.stocks': '주식 목록',
    'nav.portfolios': '포트폴리오',
    'nav.filters': '필터',
    'nav.backtest': '백테스트',
    'nav.debate': '토론',
    'nav.agents': '에이전트 빌더',
    'nav.alerts': '알림',
    'nav.settings': '설정',
    'nav.users': '사용자',
    'app.title': '주식 분석',
    'app.subtitle': 'AI 투자 플랫폼',
    'chat.title': '투자 분석 채팅',
    'chat.placeholder': '질문 입력…  / 스킬  @ 에이전트',
    'chat.send': '전송',
    'chat.hint': '질문 입력 · / 스킬 목록 · @ 에이전트 지정',
    'common.loading': '로딩 중…',
    'common.delete': '삭제',
    'common.cancel': '취소',
    'common.save': '저장',
  },
}

const saved = (localStorage.getItem('lang') as Lang) || 'zh'
export const locale = ref<Lang>(saved)

export function setLocale(lang: Lang) {
  locale.value = lang
  localStorage.setItem('lang', lang)
}

export function t(key: string): string {
  return dict[locale.value]?.[key] ?? dict.zh?.[key] ?? key
}
