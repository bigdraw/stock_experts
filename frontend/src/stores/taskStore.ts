import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useTaskStore = defineStore('task', () => {
  const activeTaskId = ref<string | null>(null)

  function setActiveTask(taskId: string | null) {
    activeTaskId.value = taskId
  }

  function clearActiveTask() {
    activeTaskId.value = null
  }

  return {
    activeTaskId,
    setActiveTask,
    clearActiveTask,
  }
})
