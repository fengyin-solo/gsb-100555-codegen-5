<template>
  <div>
    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>预案编号 / 名称</span>
        <input v-model="keyword" placeholder="按预案编号或名称检索" />
      </label>
      <label class="filter-item">
        <span>电站</span>
        <input v-model="station" placeholder="按电站筛选" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <button class="btn primary" type="button" @click="showCreate = true">登记预案</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="open(Number(row.id))">版本与演练</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无预案，可先登记或通过导入记录批量导入</td>
        </tr>
      </tbody>
    </table>
    <footer class="page-foot"><span>共 {{ total }} 份预案（{{ year }} 年覆盖率口径）</span></footer>

    <PlanCreate v-if="showCreate" @close="showCreate = false" @done="onCreated" />
    <PlanDetail v-if="detailId" :plan-id="detailId" :year="year" @close="detailId = null" @changed="reload" @message="emitMessage" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getPage } from '../api'
import PlanCreate from './PlanCreate.vue'
import PlanDetail from './PlanDetail.vue'

const props = defineProps<{ year: number }>()
const emit = defineEmits<{ message: [message: string, ok: boolean] }>()

const columns = [
  '预案编号', '预案名称', '电站', '当前版本', '发布日期', '批复人',
  '版本数', '事故类别数', '本年度覆盖率', '本年度演练数', '待整改项', 'status',
]
const rows = ref<Record<string, unknown>[]>([])
const total = ref(0)
const keyword = ref('')
const station = ref('')
const showCreate = ref(false)
const detailId = ref<number | null>(null)

function emitMessage(message: string, ok = true) {
  emit('message', message, ok)
}

async function reload() {
  const params = new URLSearchParams({ year: String(props.year) })
  if (keyword.value) params.set('keyword', keyword.value)
  if (station.value) params.set('station', station.value)
  const page = await getPage(`?${params.toString()}`)
  rows.value = page.items
  total.value = page.total
}

function resetFilters() {
  keyword.value = ''
  station.value = ''
  void reload()
}

function open(id: number) {
  detailId.value = id
}

function onCreated(message: string) {
  showCreate.value = false
  emitMessage(message)
  void reload()
}

onMounted(reload)
defineExpose({ reload })
</script>
