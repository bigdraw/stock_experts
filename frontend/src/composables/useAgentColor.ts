/** agent 颜色 hash → 暖色调色板（活泼可爱风）。chat/debate/任何渲染 agent 气泡的视图复用。 */
const AGENT_COLORS = ['#FF6B5C', '#FFC857', '#5BA882', '#9B7BC4', '#5B8FB9', '#F4A6B0', '#F08A4B', '#4FB0BF']

export function agentColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length]
}

export function useAgentColor() {
  return { agentColor, AGENT_COLORS }
}
