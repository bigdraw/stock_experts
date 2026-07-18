<template>
  <n-space vertical>
    <n-card title="系统设置">
      <n-space vertical :size="24">
        <!-- Network Settings -->
        <n-space vertical :size="12">
          <n-h3>网络设置</n-h3>
          <n-space align="center" :size="16">
            <n-switch
              v-model:value="proxyEnabled"
              @update:value="handleProxyChange"
            />
            <n-text>使用系统代理</n-text>
          </n-space>
          <n-space>
            <n-button
              @click="testConnection"
              :loading="testing"
              :disabled="testing"
            >
              测试连接
            </n-button>
          </n-space>
          <n-alert
            v-if="testResult"
            :type="testResult.success ? 'success' : 'error'"
            :title="testResult.message"
            style="margin-top: 12px"
          />
        </n-space>

        <!-- LLM Configuration -->
        <n-space vertical :size="12">
          <n-h3>LLM 配置</n-h3>
          <n-p>当前 Provider: qwen3.7-max (通过 config.yaml 配置)</n-p>
        </n-space>

        <!-- Data Source -->
        <n-space vertical :size="12">
          <n-h3>数据源</n-h3>
          <n-p>当前 Provider: akshare (免费)</n-p>
        </n-space>

        <!-- Backtest Friction Costs -->
        <n-space vertical :size="12">
          <n-h3>回测摩擦成本</n-h3>
          <n-descriptions :column="2" bordered>
            <n-descriptions-item label="印花税">0.05%（卖出单边）</n-descriptions-item>
            <n-descriptions-item label="佣金">0.025%（买卖各）</n-descriptions-item>
            <n-descriptions-item label="最低佣金">5 元</n-descriptions-item>
            <n-descriptions-item label="滑点">0.1%</n-descriptions-item>
          </n-descriptions>
        </n-space>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { settingsApi, tasksApi } from '../api'

const message = useMessage()
const dialog = useDialog()

const proxyEnabled = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)

onMounted(async () => {
  try {
    const res = await settingsApi.getProxy()
    proxyEnabled.value = res.data.enabled
  } catch (e: any) {
    message.error('加载代理设置失败: ' + (e.response?.data?.detail || e.message))
  }
})

async function handleProxyChange(value: boolean) {
  // Check for running tasks
  try {
    const tasksRes = await tasksApi.list()
    const runningTasks = tasksRes.data.filter((t: any) =>
      t.status === 'running' || t.status === 'paused'
    )

    if (runningTasks.length > 0) {
      // Show confirmation dialog
      dialog.warning({
        title: '确认切换',
        content: `当前有 ${runningTasks.length} 个任务正在运行，切换代理设置可能会影响这些任务。是否继续？`,
        positiveText: '继续',
        negativeText: '取消',
        onPositiveClick: async () => {
          await updateProxySetting(value)
        },
        onNegativeClick: () => {
          // Revert the switch
          proxyEnabled.value = !value
        },
      })
    } else {
      await updateProxySetting(value)
    }
  } catch (e: any) {
    message.error('检查任务状态失败: ' + (e.response?.data?.detail || e.message))
    // Revert the switch
    proxyEnabled.value = !value
  }
}

async function updateProxySetting(value: boolean) {
  try {
    await settingsApi.setProxy(value)
    proxyEnabled.value = value
    message.success('代理设置已更新')
  } catch (e: any) {
    message.error('更新代理设置失败: ' + (e.response?.data?.detail || e.message))
    // Revert the switch
    proxyEnabled.value = !value
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    const res = await settingsApi.testConnection()
    testResult.value = res.data
  } catch (e: any) {
    testResult.value = {
      success: false,
      message: e.response?.data?.message || e.message || '测试连接失败'
    }
  } finally {
    testing.value = false
  }
}
</script>
