<template>
  <div class="login-container">
    <!-- 背景动画效果 -->
    <div class="background-effects">
      <div class="glow glow-1"></div>
      <div class="glow glow-2"></div>
      <div class="glow glow-3"></div>
    </div>

    <!-- 登录卡片 -->
    <div class="login-card glass">
      <div class="card-header">
        <h1 class="title gradient-text">股票分析平台</h1>
        <p class="subtitle">智能投资 · 数据驱动 · AI赋能</p>
      </div>

      <n-tabs type="segment" animated>
        <n-tab-pane name="login" tab="登录">
          <n-form class="login-form">
            <n-form-item label="用户名">
              <n-input 
                v-model:value="username" 
                placeholder="请输入用户名"
                size="large"
              >
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <PersonOutline />
                  </n-icon>
                </template>
              </n-input>
            </n-form-item>
            
            <n-form-item label="密码">
              <n-input 
                v-model:value="password" 
                type="password" 
                placeholder="请输入密码"
                size="large"
                show-password-on="click"
                @keyup.enter="handleLogin"
              >
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <LockClosedOutline />
                  </n-icon>
                </template>
              </n-input>
            </n-form-item>
            
            <n-button 
              type="primary" 
              block 
              size="large"
              :loading="loading" 
              @click="handleLogin"
              class="login-button"
            >
              登录
            </n-button>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="register" tab="注册">
          <n-form class="login-form">
            <n-form-item label="用户名">
              <n-input 
                v-model:value="regUsername" 
                placeholder="请输入用户名"
                size="large"
              >
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <PersonOutline />
                  </n-icon>
                </template>
              </n-input>
            </n-form-item>
            
            <n-form-item label="密码">
              <n-input 
                v-model:value="regPassword" 
                type="password" 
                placeholder="请输入密码（至少6位）"
                size="large"
                show-password-on="click"
                @keyup.enter="handleRegister"
              >
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <LockClosedOutline />
                  </n-icon>
                </template>
              </n-input>
            </n-form-item>
            
            <n-button 
              type="primary" 
              block 
              size="large"
              :loading="loading" 
              @click="handleRegister"
              class="login-button"
            >
              注册
            </n-button>
          </n-form>
        </n-tab-pane>
      </n-tabs>

      <div class="card-footer">
        <p class="footer-text">
          <n-icon :size="14" color="#64748b">
            <ShieldCheckmarkOutline />
          </n-icon>
          安全加密 · 数据保护
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { 
  PersonOutline, 
  LockClosedOutline, 
  ShieldCheckmarkOutline 
} from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const regUsername = ref('')
const regPassword = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!username.value.trim()) {
    message.warning('请输入用户名')
    return
  }
  if (!password.value) {
    message.warning('请输入密码')
    return
  }
  loading.value = true
  try {
    await authStore.login(username.value.trim(), password.value)
    router.push('/')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!regUsername.value.trim()) {
    message.warning('请输入用户名')
    return
  }
  if (!regPassword.value || regPassword.value.length < 6) {
    message.warning('密码长度至少6位')
    return
  }
  loading.value = true
  try {
    await authStore.register(regUsername.value.trim(), regPassword.value)
    router.push('/')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-base);
  overflow: hidden;
}

/* 背景动画效果 */
.background-effects {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  pointer-events: none;
}

.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  opacity: 0.3;
  animation: float 20s ease-in-out infinite;
}

.glow-1 {
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, #00d4aa 0%, transparent 70%);
  top: -10%;
  left: -10%;
  animation-delay: 0s;
}

.glow-2 {
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, #6366f1 0%, transparent 70%);
  bottom: -10%;
  right: -10%;
  animation-delay: 7s;
}

.glow-3 {
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, #10b981 0%, transparent 70%);
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation-delay: 14s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(50px, -50px) scale(1.1);
  }
  66% {
    transform: translate(-50px, 50px) scale(0.9);
  }
}

/* 登录卡片 */
.login-card {
  position: relative;
  width: 100%;
  max-width: 440px;
  padding: 48px 40px;
  border-radius: 20px;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border-medium);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  animation: slideUp 0.5s ease-out;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.card-header {
  text-align: center;
  margin-bottom: 32px;
}

.title {
  font-size: 32px;
  font-weight: 700;
  margin: 0 0 8px 0;
  letter-spacing: -0.5px;
}

.subtitle {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
  letter-spacing: 1px;
}

/* 表单样式 */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.login-form :deep(.n-form-item) {
  margin-bottom: 0;
}

.login-form :deep(.n-form-item-label) {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.login-form :deep(.n-input) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 10px !important;
  transition: all 0.3s !important;
}

.login-form :deep(.n-input:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.login-form :deep(.n-input--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(0, 212, 170, 0.15) !important;
  background: rgba(30, 41, 59, 0.9) !important;
}

/* 登录按钮 */
.login-button {
  margin-top: 8px;
  height: 48px !important;
  font-size: 16px !important;
  font-weight: 600 !important;
  border-radius: 10px !important;
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%) !important;
  border: none !important;
  transition: all 0.3s !important;
  position: relative;
  overflow: hidden;
}

.login-button::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.3),
    transparent
  );
  transition: left 0.5s;
}

.login-button:hover::before {
  left: 100%;
}

.login-button:hover {
  box-shadow: 0 8px 24px rgba(0, 212, 170, 0.4) !important;
  transform: translateY(-2px);
}

.login-button:active {
  transform: translateY(0);
}

/* 卡片底部 */
.card-footer {
  margin-top: 32px;
  text-align: center;
}

.footer-text {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
}

/* Tabs 样式 */
:deep(.n-tabs) {
  margin-bottom: 24px;
}

:deep(.n-tabs-nav) {
  background: rgba(30, 41, 59, 0.6);
  border-radius: 10px;
  padding: 4px;
}

:deep(.n-tabs-tab) {
  border-radius: 8px;
  font-weight: 600;
  transition: all 0.3s;
}

:deep(.n-tabs-tab--active) {
  background: linear-gradient(135deg, rgba(0, 212, 170, 0.2) 0%, rgba(99, 102, 241, 0.2) 100%);
  color: var(--primary);
}

/* 响应式 */
@media (max-width: 480px) {
  .login-card {
    margin: 20px;
    padding: 32px 24px;
  }

  .title {
    font-size: 28px;
  }
}
</style>
