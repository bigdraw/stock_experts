<template>
  <div class="admin-container">
    <div class="page-header">
      <h1 class="gradient-text">用户管理</h1>
      <p class="subtitle">管理系统用户账号</p>
    </div>

    <n-card class="admin-card">
      <template #header>
        <div class="card-header">
          <span>用户列表</span>
          <n-tag type="info" size="small">共 {{ users.length }} 个用户</n-tag>
        </div>
      </template>

      <n-data-table
        :columns="columns"
        :data="users"
        :loading="loading"
        :bordered="false"
        :single-line="false"
      />
    </n-card>

    <!-- Reset Password Modal -->
    <n-modal v-model:show="showResetModal" preset="dialog" title="重置密码">
      <n-form>
        <n-form-item label="新密码">
          <n-input
            v-model:value="newPassword"
            type="password"
            show-password-on="click"
            placeholder="请输入新密码（至少6位）"
          />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button @click="showResetModal = false">取消</n-button>
        <n-button type="primary" @click="handleResetPassword" :loading="resetting">
          确认重置
        </n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NButton, NTag, NSwitch, useMessage, useDialog } from 'naive-ui'
import { 
  RefreshOutline, 
  TrashOutline, 
  ShieldCheckmarkOutline, 
  ShieldOutline 
} from '@vicons/ionicons5'
import { adminApi } from '../api'
import type { AdminUser } from '../types'

const message = useMessage()
const dialog = useDialog()

const users = ref<AdminUser[]>([])
const loading = ref(false)
const showResetModal = ref(false)
const resetting = ref(false)
const newPassword = ref('')
const selectedUserId = ref<number | null>(null)

const columns = [
  {
    title: 'ID',
    key: 'id',
    width: 80,
  },
  {
    title: '用户名',
    key: 'username',
    render(row: AdminUser) {
      return h('div', { class: 'username-cell' }, [
        h('span', { class: 'username' }, row.username),
        row.role === 'admin' && h(NTag, { 
          type: 'warning', 
          size: 'small',
          style: 'margin-left: 8px'
        }, { default: () => '管理员' })
      ])
    }
  },
  {
    title: '角色',
    key: 'role',
    width: 120,
    render(row: AdminUser) {
      return h(NTag, {
        type: row.role === 'admin' ? 'warning' : 'default',
        size: 'small'
      }, { default: () => row.role === 'admin' ? '管理员' : '普通用户' })
    }
  },
  {
    title: '状态',
    key: 'is_active',
    width: 100,
    render(row: AdminUser) {
      return h(NSwitch, {
        value: row.is_active,
        onUpdateValue: (value: boolean) => handleToggleStatus(row, value)
      })
    }
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
    render(row: AdminUser) {
      return new Date(row.created_at).toLocaleString('zh-CN')
    }
  },
  {
    title: '操作',
    key: 'actions',
    width: 280,
    render(row: AdminUser) {
      return h('div', { class: 'action-buttons' }, [
        h(NButton, {
          size: 'small',
          type: 'info',
          ghost: true,
          onClick: () => openResetModal(row)
        }, {
          icon: () => h(RefreshOutline),
          default: () => '重置密码'
        }),
        h(NButton, {
          size: 'small',
          type: row.role === 'admin' ? 'default' : 'warning',
          ghost: true,
          onClick: () => handleToggleRole(row)
        }, {
          icon: () => h(row.role === 'admin' ? ShieldOutline : ShieldCheckmarkOutline),
          default: () => row.role === 'admin' ? '降级' : '升级'
        }),
        h(NButton, {
          size: 'small',
          type: 'error',
          ghost: true,
          onClick: () => handleDelete(row)
        }, {
          icon: () => h(TrashOutline),
          default: () => '删除'
        })
      ])
    }
  }
]

async function loadUsers() {
  loading.value = true
  try {
    const res = await adminApi.listUsers()
    users.value = res.data
  } catch (error: any) {
    message.error('加载用户列表失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

function openResetModal(user: AdminUser) {
  selectedUserId.value = user.id
  newPassword.value = ''
  showResetModal.value = true
}

async function handleResetPassword() {
  if (!selectedUserId.value) return
  
  if (newPassword.value.length < 6) {
    message.warning('密码长度至少6位')
    return
  }

  resetting.value = true
  try {
    await adminApi.resetPassword(selectedUserId.value, newPassword.value)
    message.success('密码重置成功')
    showResetModal.value = false
    await loadUsers()
  } catch (error: any) {
    message.error('重置密码失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    resetting.value = false
  }
}

async function handleToggleStatus(user: AdminUser, isActive: boolean) {
  try {
    await adminApi.updateUserStatus(user.id, isActive)
    message.success(`用户 ${user.username} 已${isActive ? '启用' : '禁用'}`)
    await loadUsers()
  } catch (error: any) {
    message.error('更新状态失败: ' + (error.response?.data?.detail || error.message))
  }
}

async function handleToggleRole(user: AdminUser) {
  const newRole = user.role === 'admin' ? 'user' : 'admin'
  const action = newRole === 'admin' ? '升级为管理员' : '降级为普通用户'
  
  dialog.warning({
    title: `确认${action}`,
    content: `确定要将用户 ${user.username} ${action}吗？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await adminApi.updateUserRole(user.id, newRole)
        message.success(`用户 ${user.username} 已${action}`)
        await loadUsers()
      } catch (error: any) {
        message.error('更新角色失败: ' + (error.response?.data?.detail || error.message))
      }
    }
  })
}

async function handleDelete(user: AdminUser) {
  dialog.error({
    title: '确认删除',
    content: `确定要删除用户 ${user.username} 吗？此操作不可恢复！`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await adminApi.deleteUser(user.id)
        message.success(`用户 ${user.username} 已删除`)
        await loadUsers()
      } catch (error: any) {
        message.error('删除用户失败: ' + (error.response?.data?.detail || error.message))
      }
    }
  })
}

onMounted(() => {
  loadUsers()
})
</script>

<style scoped>
.admin-container {
  padding: 24px;
  animation: fadeIn 0.3s ease-out;
}

.page-header {
  margin-bottom: 32px;
}

.page-header h1 {
  font-size: 32px;
  font-weight: 700;
  margin: 0 0 8px 0;
}

.subtitle {
  color: var(--text-tertiary);
  font-size: 14px;
  margin: 0;
}

.admin-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.username-cell {
  display: flex;
  align-items: center;
}

.username {
  font-weight: 500;
  color: var(--text-primary);
}

.action-buttons {
  display: flex;
  gap: 8px;
}

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
</style>
