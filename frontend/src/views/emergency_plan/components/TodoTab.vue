<template>
  <div>
    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>状态</span>
        <select v-model="status">
          <option value="">全部</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="status = ''; void reload()">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>来源演练</th>
          <th>电站</th>
          <th>整改内容</th>
          <th>责任人</th>
          <th>整改期限</th>
          <th>状态</th>
          <th>闭环日期</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row.演练编号 }} {{ row.演练名称 }}</td>
          <td>{{ row.电站 }}</td>
          <td>{{ row.整改内容 }}</td>
          <td>{{ row.责任人 || '—' }}</td>
          <td :class="{ overdue: isOverdue(row) }">{{ row.整改期限 || '—' }}</td>
          <td>{{ row.status }}</td>
          <td>{{ row.闭环日期 || '—' }}</td>
          <td class="row-actions">
            <button v-if="row.status === '待整改'" class="link" type="button" @click="act(row.id, '认领整改')">
              认领整改
            </button>
            <button v-if="row.status !== '已闭环'" class="link" type="button" @click="act(row.id, '完成闭环')">
              完成闭环
            </button>
            <span v-else class="muted">已闭环</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="8" class="empty-state">暂无演练待办</td>
        </tr>
      </tbody>
    </table>
    <footer class="page-foot"><span>共 {{ total }} 条待办，默认未闭环、临期在前</span></footer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchMeta, getPage, postAction, type Meta } from '../api'

const emit = defineEmits<{ message: [message: string, ok: boolean] }>()

const rows = ref<Record<string, any>[]>([])
const total = ref(0)
const status = ref('')
const statuses = ref<Meta['todo_statuses']>([])

function isOverdue(row: Record<string, any>) {
  return row.status !== '已闭环' && row.整改期限 && row.整改期限 < new Date().toISOString().slice(0, 10)
}

async function reload() {
  const query = status.value ? `?status=${encodeURIComponent(status.value)}` : ''
  const page = await getPage(`/todos${query}`)
  rows.value = page.items
  total.value = page.total
}

async function act(id: number, action: string) {
  const result = await postAction(`/todos/${id}/actions`, { action })
  emit('message', result.message, result.ok)
  if (result.ok) await reload()
}

onMounted(async () => {
  const meta = await fetchMeta()
  statuses.value = meta.todo_statuses
  await reload()
})
</script>

<style scoped>
.overdue {
  color: #b42318;
  font-weight: 600;
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
</style>
