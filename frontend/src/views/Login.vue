<template>
  <div style="max-width: 400px; margin: 100px auto">
    <n-card title="股票分析平台">
      <n-tabs type="line">
        <n-tab-pane name="login" tab="登录">
          <n-form>
            <n-form-item label="用户名">
              <n-input v-model:value="username" placeholder="用户名" />
            </n-form-item>
            <n-form-item label="密码">
              <n-input v-model:value="password" type="password" placeholder="密码" @keyup.enter="handleLogin" />
            </n-form-item>
            <n-button type="primary" block :loading="loading" @click="handleLogin">登录</n-button>
          </n-form>
        </n-tab-pane>
        <n-tab-pane name="register" tab="注册">
          <n-form>
            <n-form-item label="用户名">
              <n-input v-model:value="regUsername" placeholder="用户名" />
            </n-form-item>
            <n-form-item label="密码">
              <n-input v-model:value="regPassword" type="password" placeholder="密码" @keyup.enter="handleRegister" />
            </n-form-item>
            <n-button type="primary" block :loading="loading" @click="handleRegister">注册</n-button>
          </n-form>
        </n-tab-pane>
      </n-tabs>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
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
