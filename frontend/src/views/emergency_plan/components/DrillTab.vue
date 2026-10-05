<template>
  <div>
    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>年份</span>
        <input v-model.number="yearFilter" type="number" :placeholder="String(year)" @input="useDefaultYear" />
      </label>
      <label class="filter-item">
        <span>版本</span>
        <select v-model="versionFilter">
          <option value="">全部版本</option>
          <option value="current">仅现行版本演练</option>
          <option value="archived">仅历史版本演练</option>
        </select>
      </label>
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="keyword" placeholder="演练编号 / 名称" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '版本口径'">
              <span :class="isCurrent(row) ? 'tag-current-text' : 'tag-history-text'">
                {{ row.版本号 }}{{ isCurrent(row) ? ' ·现行' : ' ·历史' }}
              </span>
            </template>
            <template v-else>{{ formatCell(row, column) }}</template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length" class="empty-state">暂无演练记录</td>
        </tr>
      </tbody>
    </table>
    <footer class="page-foot"><span>共 {{ total }} 场演练</span></footer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getPage } from '../api'

const props = defineProps<{ year: number }>()

const columns = [
  '演练编号', '预案名称', '电站', '版本口径', '演练名称', '事故类别',
  '演练日期', '总指挥', '参演人数', '演练结论评级', '待整改数',
]
const rows = ref<Record<string, any>[]>([])
const total = ref(0)
const yearFilter = ref<number | null>(null)
const versionFilter = ref('')
const keyword = ref('')

function useDefaultYear() {
  if (!yearFilter.value) yearFilter.value = props.year
}

function isCurrent(row: Record<string, any>) {
  return currentVersionNo(row) === row.版本号
}

const currentMap = ref(new Map<number, string>())

function currentVersionNo(row: Record<string, any>) {
  return currentMap.value.get(Number(row.plan_id))
}

async function loadCurrentMap() {
  // 列表只展示“现行/历史”口径标签，现行版本号通过预案列表轻量获取。
  const page = await getPage(`?year=${props.year}&size=200`)
  currentMap.value = new Map(
    page.items.map((item) => [Number(item.id), String(item.当前版本)]),
  )
}

function formatCell(row: Record<string, any>, column: string) {
  if (column === '参演人数') return (row.参演人员 ?? []).length
  return row[column] ?? '—'
}

async function reload() {
  const params = new URLSearchParams()
  params.set('year', String(yearFilter.value ?? props.year))
  if (keyword.value) params.set('keyword', keyword.value)
  const page = await getPage(`/drills?${params.toString()}`)
  let items = page.items
  if (versionFilter.value === 'current') {
    items = items.filter((item) => currentVersionNo(item) === item.版本号)
  } else if (versionFilter.value === 'archived') {
    items = items.filter((item) => currentVersionNo(item) !== item.版本号)
  }
  rows.value = items
  total.value = versionFilter.value ? items.length : page.total
}

function resetFilters() {
  yearFilter.value = null
  versionFilter.value = ''
  keyword.value = ''
  void reload()
}

onMounted(async () => {
  await loadCurrentMap()
  await reload()
})
</script>

<style scoped>
.tag-current-text {
  color: #067647;
  font-weight: 600;
}
.tag-history-text {
  color: var(--muted);
}
</style>
