<template>
  <div>
    <div class="section-head">
      <h4>批量导入预案版本</h4>
      <div class="head-btns">
        <button class="btn small" type="button" @click="addRow">添加一行</button>
        <button class="btn small" type="button" @click="fillSample">填入示例</button>
        <button class="btn primary small" type="button" :disabled="importing" @click="submitImport">
          {{ importing ? '导入中…' : '执行导入' }}
        </button>
      </div>
    </div>
    <p class="modal-tip">
      去重口径：预案编号一致（缺编号时电站＋预案名称一致）且版本号相同视为重复，重复行只保留既有一条、不再建档；
      存量预案按发布日期回填，发布日期最新的已批复版本自动成为现行版本。每次导入都会落一条导入记录。
    </p>
    <table class="data-table import-edit">
      <thead>
        <tr>
          <th>预案编号*</th><th>预案名称*</th><th>电站*</th><th>版本号*</th>
          <th>发布日期*</th><th>批复人</th><th>事故类别（顿号分隔）</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in draft" :key="index">
          <td><input v-model="row.预案编号" /></td>
          <td><input v-model="row.预案名称" /></td>
          <td><input v-model="row.电站" /></td>
          <td><input v-model="row.版本号" /></td>
          <td><input v-model="row.发布日期" type="date" /></td>
          <td><input v-model="row.批复人" /></td>
          <td><input v-model="row.事故类别文本" placeholder="火灾、触电、防汛" /></td>
          <td><button class="link danger" type="button" @click="draft.splice(index, 1)">移除</button></td>
        </tr>
        <tr v-if="!draft.length">
          <td colspan="8" class="empty-state">点击「添加一行」或「填入示例」开始导入</td>
        </tr>
      </tbody>
    </table>

    <section class="detail-section">
      <h4>导入记录</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>导入批号</th><th>来源</th><th>导入人</th><th>导入时间</th>
            <th>总行数</th><th>新增</th><th>重复跳过</th><th>失败</th><th>明细</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="String(log.id)">
            <td>{{ log.导入批号 }}</td>
            <td>{{ log.来源 }}</td>
            <td>{{ log.导入人 }}</td>
            <td>{{ log.导入时间 }}</td>
            <td>{{ log.总行数 }}</td>
            <td class="ok-num">{{ log.新增数 }}</td>
            <td>{{ log.重复跳过数 }}</td>
            <td :class="{ 'fail-num': log.失败数 > 0 }">{{ log.失败数 }}</td>
            <td>
              <button class="link" type="button" @click="openLog(log)">查看逐行结果</button>
            </td>
          </tr>
          <tr v-if="!logs.length">
            <td colspan="9" class="empty-state">暂无导入记录</td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="viewing" class="modal-mask" @click.self="viewing = null">
      <div class="modal">
        <header class="modal-head">
          <h3>导入明细 · {{ viewing.导入批号 }}</h3>
          <button class="link" type="button" @click="viewing = null">关闭</button>
        </header>
        <div class="modal-body">
          <table class="data-table">
            <thead><tr><th>行号</th><th>结果</th><th>预案编号</th><th>版本号</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="item in viewing.明细" :key="item.行号">
                <td>{{ item.行号 }}</td>
                <td :class="resultClass(item.结果)">{{ item.结果 }}</td>
                <td>{{ item.预案编号 }}</td>
                <td>{{ item.版本号 }}</td>
                <td>{{ item.说明 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getPage, postAction } from '../api'

const emit = defineEmits<{ message: [message: string, ok: boolean] }>()

type DraftRow = {
  预案编号: string
  预案名称: string
  电站: string
  版本号: string
  发布日期: string
  批复人: string
  事故类别文本: string
}
type ImportLog = {
  id: number
  导入批号: string
  来源: string
  导入人: string
  导入时间: string
  总行数: number
  新增数: number
  重复跳过数: number
  失败数: number
  明细: { 行号: number; 结果: string; 预案编号: string; 版本号: string; 说明: string }[]
}

const draft = ref<DraftRow[]>([])
const logs = ref<ImportLog[]>([])
const importing = ref(false)
const viewing = ref<ImportLog | null>(null)

function emptyRow(): DraftRow {
  return { 预案编号: '', 预案名称: '', 电站: '', 版本号: '', 发布日期: '', 批复人: '', 事故类别文本: '' }
}

function addRow() {
  draft.value.push(emptyRow())
}

function fillSample() {
  draft.value = [
            { 预案编号: 'YJYA-YG-01', 预案名称: '光伏场区综合应急预案', 电站: '羊岗光伏电站',
              版本号: 'B/0', 发布日期: '2026-03-15', 批复人: '周建国', 事故类别文本: '火灾、触电' },
            { 预案编号: 'YJYA-HD-01', 预案名称: '河道取水口应急防护预案', 电站: '河滩光伏电站',
              版本号: '2.0', 发布日期: '2025-07-01', 批复人: '宋岩', 事故类别文本: '防汛、物体打击' },
  ]
}

async function submitImport() {
  if (!draft.value.length) {
    emit('message', '请先添加至少一行导入数据', false)
    return
  }
  importing.value = true
  try {
    const items = draft.value.map((row) => ({
      预案编号: row.预案编号,
      预案名称: row.预案名称,
      电站: row.电站,
      版本号: row.版本号,
      发布日期: row.发布日期,
      批复人: row.批复人,
      事故类别: row.事故类别文本
        .split(/[、,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    }))
    const result = await postAction('/imports', { items, source: '文档批量导入', operator: '值班管理员' })
    emit('message', result.message, result.ok)
    if (result.ok) {
      draft.value = []
      viewing.value = (result.entry as unknown as ImportLog) ?? null
    }
    await reloadLogs()
  } finally {
    importing.value = false
  }
}

function openLog(log: ImportLog) {
  viewing.value = log
}

function resultClass(result: string) {
  if (result.includes('失败')) return 'fail-num'
  if (result.includes('重复')) return 'muted'
  return 'ok-num'
}

async function reloadLogs() {
  const page = await getPage('/imports')
  logs.value = page.items as ImportLog[]
}

onMounted(reloadLogs)
</script>

<style scoped>
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 12px 0 6px;
}
.head-btns {
  display: flex;
  gap: 8px;
}
.import-edit input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 6px;
  font-size: 12px;
}
.detail-section {
  margin-top: 20px;
}
.detail-section h4 {
  font-size: 14px;
}
.small {
  padding: 4px 10px;
  font-size: 12px;
}
.ok-num {
  color: #067647;
}
.fail-num {
  color: #b42318;
  font-weight: 600;
}
.muted {
  color: var(--muted);
}
.danger {
  color: #b42318;
}
</style>
