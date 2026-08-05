/** agent 颜色 hash → 调色板。通用，chat/debate/任何渲染 agent 气泡的视图复用。 */
const AGENT_COLORS = ['#e94560', '#0f9b8e', '#f5a623', '#5856d6', '#007aff', '#34c759', '#ff9500', '#af52de']

export function agentColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length]
}

export function useAgentColor() {
  return { agentColor, AGENT_COLORS }
}
