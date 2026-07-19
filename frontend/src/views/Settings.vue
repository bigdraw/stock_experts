<template>
  <div class="page-container">
    <n-space vertical :size="24">
      <n-card title="系统设置" class="settings-card">
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
                class="action-button"
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
            <n-form label-placement="left" label-width="120">
              <n-form-item label="Provider">
                <n-input v-model:value="llmConfig.provider" />
              </n-form-item>
              <n-form-item label="Base URL">
                <n-input v-model:value="llmConfig.base_url" />
              </n-form-item>
              <n-form-item label="API Key">
                <n-input
                  v-model:value="llmConfig.api_key"
                  :type="showApiKey ? 'text' : 'password'"
                  show-password-on="click"
                >
                  <template #suffix>
                    <n-button text @click="showApiKey = !showApiKey">
                      {{ showApiKey ? '隐藏' : '显示' }}
                    </n-button>
                  </template>
                </n-input>
              </n-form-item>
              <n-form-item label="Model">
                <n-input v-model:value="llmConfig.model" />
              </n-form-item>
              <n-form-item label="Max Tokens">
                <n-input-number v-model:value="llmConfig.max_tokens" :min="1" :max="1000000" />
              </n-form-item>
              <n-form-item label="Temperature">
                <n-slider
                  v-model:value="llmConfig.temperature"
                  :min="0"
                  :max="2"
                  :step="0.1"
                  :format-tooltip="(v: number) => v.toFixed(1)"
                />
                <n-text depth="3" style="margin-left: 12px">{{ llmConfig.temperature.toFixed(1) }}</n-text>
              </n-form-item>
            </n-form>
            <n-space>
              <n-button @click="saveLLM" :loading="savingLLM" class="action-button">保存</n-button>
              <n-button @click="testLLM" :loading="testingLLM" class="action-button">测试 LLM 连接</n-button>
            </n-space>
            <n-alert
              v-if="llmTestResult"
              :type="llmTestResult.success ? 'success' : 'error'"
              :title="llmTestResult.message"
              style="margin-top: 12px"
            />
          </n-space>

          <!-- Data Source Configuration -->
          <n-space vertical :size="12">
            <n-h3>数据源配置</n-h3>
            <n-form label-placement="left" label-width="120">
              <n-form-item label="Provider">
                <n-input v-model:value="dataSourceConfig.provider" />
              </n-form-item>
              <n-form-item label="Rate Limit">
                <n-input-number v-model:value="dataSourceConfig.rate_limit" :min="1" :max="100" />
              </n-form-item>
              <n-form-item label="Retry Max">
                <n-input-number v-model:value="dataSourceConfig.retry_max" :min="1" :max="10" />
              </n-form-item>
            </n-form>
            <n-button @click="saveDataSource" :loading="savingDataSource" class="action-button">保存</n-button>
          </n-space>

          <!-- Backtest Friction Costs -->
          <n-space vertical :size="12">
            <n-h3>回测摩擦成本</n-h3>
            <n-form label-placement="left" label-width="120">
              <n-form-item label="印花税">
                <n-input-number
                  v-model:value="frictionConfig.stamp_tax"
                  :min="0"
                  :max="0.01"
                  :step="0.0001"
                  :format-tooltip="(v: number) => (v * 100).toFixed(4) + '%'"
                />
                <n-text depth="3" style="margin-left: 12px">{{ (frictionConfig.stamp_tax * 100).toFixed(4) }}%</n-text>
              </n-form-item>
              <n-form-item label="佣金">
                <n-input-number
                  v-model:value="frictionConfig.commission"
                  :min="0"
                  :max="0.01"
                  :step="0.0001"
                  :format-tooltip="(v: number) => (v * 100).toFixed(4) + '%'"
                />
                <n-text depth="3" style="margin-left: 12px">{{ (frictionConfig.commission * 100).toFixed(4) }}%</n-text>
              </n-form-item>
              <n-form-item label="最低佣金">
                <n-input-number v-model:value="frictionConfig.commission_min" :min="0" :max="100" :step="1" />
                <n-text depth="3" style="margin-left: 12px">元</n-text>
              </n-form-item>
              <n-form-item label="滑点">
                <n-input-number
                  v-model:value="frictionConfig.slippage"
                  :min="0"
                  :max="0.01"
                  :step="0.0001"
                  :format-tooltip="(v: number) => (v * 100).toFixed(4) + '%'"
                />
                <n-text depth="3" style="margin-left: 12px">{{ (frictionConfig.slippage * 100).toFixed(4) }}%</n-text>
              </n-form-item>
            </n-form>
            <n-button @click="saveFriction" :loading="savingFriction" class="action-button">保存</n-button>
          </n-space>
        </n-space>
      </n-card>
    </n-space>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { settingsApi, tasksApi } from '../api'
import type { LLMConfig, DataSourceConfig, FrictionConfig } from '../api'

const message = useMessage()
const dialog = useDialog()

// Proxy settings
const proxyEnabled = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)

// LLM settings
const llmConfig = ref<LLMConfig>({
  provider: '',
  base_url: '',
  api_key: '',
  model: '',
  max_tokens: 65536,
  temperature: 0.7,
})
const showApiKey = ref(false)
const savingLLM = ref(false)
const testingLLM = ref(false)
const llmTestResult = ref<{ success: boolean; message: string } | null>(null)

// Data source settings
const dataSourceConfig = ref<DataSourceConfig>({
  provider: '',
  rate_limit: 10,
  retry_max: 3,
})
const savingDataSource = ref(false)

// Friction settings
const frictionConfig = ref<FrictionConfig>({
  stamp_tax: 0.0005,
  commission: 0.00025,
  commission_min: 5.0,
  slippage: 0.001,
})
const savingFriction = ref(false)

onMounted(async () => {
  try {
    // Load proxy setting
    const proxyRes = await settingsApi.getProxy()
    proxyEnabled.value = proxyRes.data.enabled

    // Load LLM setting
    const llmRes = await settingsApi.getLLM()
    llmConfig.value = llmRes.data

    // Load data source setting
    const dsRes = await settingsApi.getDataSource()
    dataSourceConfig.value = dsRes.data

    // Load friction setting
    const frRes = await settingsApi.getFriction()
    frictionConfig.value = frRes.data
  } catch (e: any) {
    message.error('加载设置失败: ' + (e.response?.data?.detail || e.message))
  }
})

// Proxy handlers
async function handleProxyChange(value: boolean) {
  try {
    const tasksRes = await tasksApi.list()
    const runningTasks = tasksRes.data.filter((t: any) =>
      t.status === 'running' || t.status === 'paused'
    )

    if (runningTasks.length > 0) {
      dialog.warning({
        title: '确认切换',
        content: `当前有 ${runningTasks.length} 个任务正在运行，切换代理设置可能会影响这些任务。是否继续？`,
        positiveText: '继续',
        negativeText: '取消',
        onPositiveClick: async () => {
          await updateProxySetting(value)
        },
        onNegativeClick: () => {
          proxyEnabled.value = !value
        },
      })
    } else {
      await updateProxySetting(value)
    }
  } catch (e: any) {
    message.error('检查任务状态失败: ' + (e.response?.data?.detail || e.message))
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

// LLM handlers
async function saveLLM() {
  savingLLM.value = true
  try {
    const res = await settingsApi.setLLM(llmConfig.value)
    llmConfig.value = res.data
    message.success('LLM 配置已保存')
  } catch (e: any) {
    message.error('保存 LLM 配置失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    savingLLM.value = false
  }
}

async function testLLM() {
  testingLLM.value = true
  llmTestResult.value = null
  try {
    const res = await settingsApi.testLLM()
    llmTestResult.value = res.data
  } catch (e: any) {
    llmTestResult.value = {
      success: false,
      message: e.response?.data?.message || e.message || '测试 LLM 连接失败'
    }
  } finally {
    testingLLM.value = false
  }
}

// Data source handlers
async function saveDataSource() {
  savingDataSource.value = true
  try {
    const res = await settingsApi.setDataSource(dataSourceConfig.value)
    dataSourceConfig.value = res.data
    message.success('数据源配置已保存')
  } catch (e: any) {
    message.error('保存数据源配置失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    savingDataSource.value = false
  }
}

// Friction handlers
async function saveFriction() {
  savingFriction.value = true
  try {
    const res = await settingsApi.setFriction(frictionConfig.value)
    frictionConfig.value = res.data
    message.success('摩擦成本配置已保存')
  } catch (e: any) {
    message.error('保存摩擦成本配置失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    savingFriction.value = false
  }
}
</script>

<style scoped>
.page-container {
  animation: fadeIn 0.3s ease-out;
}

.settings-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  transition: all 0.3s;
}

.settings-card:hover {
  border-color: var(--border-medium) !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.settings-card :deep(.n-card-header) {
  border-bottom: 1px solid var(--border-subtle);
}

.settings-card :deep(.n-card-header__main) {
  font-weight: 600;
  font-size: 18px;
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.settings-card :deep(.n-h3) {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border-subtle);
}

.settings-card :deep(.n-form-item-label) {
  font-weight: 500;
  color: var(--text-secondary);
}

.settings-card :deep(.n-input) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.settings-card :deep(.n-input:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.settings-card :deep(.n-input--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 2px rgba(0, 212, 170, 0.15) !important;
  background: rgba(30, 41, 59, 0.9) !important;
}

.settings-card :deep(.n-input-number) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.settings-card :deep(.n-input-number:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.settings-card :deep(.n-input-number--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 2px rgba(0, 212, 170, 0.15) !important;
  background: rgba(30, 41, 59, 0.9) !important;
}

.action-button {
  background: linear-gradient(135deg, rgba(0, 212, 170, 0.1) 0%, rgba(99, 102, 241, 0.1) 100%) !important;
  border: 1px solid var(--border-medium) !important;
  transition: all 0.3s !important;
}

.action-button:hover {
  background: linear-gradient(135deg, rgba(0, 212, 170, 0.2) 0%, rgba(99, 102, 241, 0.2) 100%) !important;
  border-color: var(--primary) !important;
  box-shadow: 0 0 20px rgba(0, 212, 170, 0.3) !important;
  transform: translateY(-1px);
}

.settings-card :deep(.n-switch__rail) {
  background: rgba(30, 41, 59, 0.8);
}

.settings-card :deep(.n-switch__rail--active) {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%);
}

.settings-card :deep(.n-slider-rail) {
  background: rgba(30, 41, 59, 0.8);
}

.settings-card :deep(.n-slider-rail__fill) {
  background: linear-gradient(90deg, #00d4aa 0%, #6366f1 100%);
}

.settings-card :deep(.n-slider-handle) {
  background: var(--bg-elevated);
  border: 2px solid var(--primary);
  box-shadow: 0 0 10px rgba(0, 212, 170, 0.3);
}
</style>
