<template>
  <section class="page" data-module="emergency_plan">
    <header class="page-head">
      <div>
        <h2>应急预案演练台账</h2>
        <p class="page-desc">
          一份预案按版本管理：改一版存一版，已批复版本冻结留痕；演练挂版本，覆盖率随现行版本重算，历史演练沿用原版本口径。
        </p>
      </div>
      <div class="page-actions">
        <label class="year-picker">
          统计年份
          <input v-model.number="year" type="number" min="2000" max="2100" @change="reloadStats" />
        </label>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ alert: item.label.includes('逾期') && Number(item.value) > 0 }">
          {{ item.value }}
        </strong>
      </article>
    </div>

    <nav class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <PlanTab v-if="activeTab === 'plans'" :year="year" @message="notify" />
    <DrillTab v-else-if="activeTab === 'drills'" :year="year" @message="notify" />
    <TodoTab v-else-if="activeTab === 'todos'" @message="notify" />
    <ImportTab v-else @message="notify" />

    <footer class="page-foot">
      <span>口径：覆盖率＝版本声明事故类别中本年度已演练类别数 ÷ 声明类别总数；历史演练不随换版迁移。</span>
      <span v-if="toast" class="error-text" :class="{ ok: toastOk }">{{ toast }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchStats, type Stats } from './api'
import PlanTab from './components/PlanTab.vue'
import DrillTab from './components/DrillTab.vue'
import TodoTab from './components/TodoTab.vue'
import ImportTab from './components/ImportTab.vue'

const tabs = [
  { key: 'plans', label: '预案版本台账' },
  { key: 'drills', label: '演练记录' },
  { key: 'todos', label: '演练待办' },
  { key: 'imports', label: '导入记录' },
] as const

const activeTab = ref<(typeof tabs)[number]['key']>('plans')
const year = ref(new Date().getFullYear())
const stats = ref<Stats['cards']>([])
const toast = ref('')
const toastOk = ref(false)

function notify(message: string, ok = true) {
  toast.value = message
  toastOk.value = ok
  window.setTimeout(() => {
    if (toast.value === message) toast.value = ''
  }, 4000)
}

async function reloadStats() {
  try {
    const payload = await fetchStats(year.value)
    stats.value = payload.cards
  } catch (error) {
    notify(error instanceof Error ? error.message : '看板数据读取失败', false)
  }
}

onMounted(reloadStats)
</script>

<style scoped>
.year-picker {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}
.year-picker input {
  width: 90px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.tab-bar {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}
.tab-btn {
  border: none;
  background: none;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
  color: var(--muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab-btn.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
  font-weight: 600;
}
.alert {
  color: #b42318;
}
.error-text.ok {
  color: #067647;
}
</style>
