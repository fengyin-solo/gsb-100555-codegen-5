<template>
  <div class="modal-mask wide" @click.self="$emit('close')">
    <div class="modal">
      <header class="modal-head">
        <h3>{{ plan?.预案名称 }} · 版本与演练</h3>
        <button class="link" type="button" @click="$emit('close')">关闭</button>
      </header>

      <div class="modal-body" v-if="plan">
        <p class="modal-tip">
          {{ plan.电站 }} ｜ 编号 {{ plan.预案编号 }} ｜ 现行版本：
          <strong>{{ plan.current_version?.版本号 ?? '无' }}</strong>
          （{{ plan.current_version?.发布日期 ?? '—' }} 批复）
        </p>

        <section class="detail-section">
          <div class="section-head">
            <h4>版本沿革（改一版存一版，已批复版本只读）</h4>
            <button class="btn primary small" type="button" @click="startCreateVersion">新建下一版草稿</button>
          </div>
          <table class="data-table">
            <thead>
              <tr>
                <th>版本号</th>
                <th>状态</th>
                <th>事故类别（覆盖率口径）</th>
                <th>发布日期</th>
                <th>批复人</th>
                <th>{{ year }}年覆盖率</th>
                <th>累计覆盖率</th>
                <th>演练场次</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="version in plan.versions" :key="version.id" :class="{ current: version.is_current }">
                <td>
                  {{ version.版本号 }}
                  <span v-if="version.is_current" class="tag tag-current">现行</span>
                </td>
                <td>{{ version.status }}</td>
                <td>{{ version.事故类别.join('、') || '—' }}</td>
                <td>{{ version.发布日期 || '—' }}</td>
                <td>{{ version.批复人 || '—' }}</td>
                <td>
                  <strong :class="coverageClass(version.coverage_year.rate)">
                    {{ version.coverage_year.rate }}%
                  </strong>
                  （{{ version.coverage_year.covered_count }}/{{ version.coverage_year.total_types }}）
                </td>
                <td>{{ version.coverage_all.rate }}%（{{ version.coverage_all.covered_count }}/{{ version.coverage_all.total_types }}）</td>
                <td>{{ version.演练场次 }}</td>
                <td class="row-actions">
                  <button class="link" type="button" @click="viewVersion(version)">查看内容</button>
                  <template v-if="version.status === '草稿'">
                    <button class="link" type="button" @click="editVersion(version)">编辑</button>
                    <button class="link" type="button" @click="act(version.id, '提交批复')">提交批复</button>
                    <button class="link danger" type="button" @click="discard(version.id)">作废</button>
                  </template>
                  <button v-if="version.status === '待批复'" class="link" type="button" @click="act(version.id, '撤回批复')">撤回</button>
                  <button v-if="version.status === '待批复'" class="link" type="button" @click="openApprove(version)">批复</button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="!plan.versions.length" class="empty-state">尚未建立任何版本</p>
        </section>

        <section class="detail-section">
          <div class="section-head">
            <h4>演练记录（归档到当时版本，换版不迁移）</h4>
            <button class="btn small" type="button" @click="showDrillCreate = true">登记演练</button>
          </div>
          <table class="data-table">
            <thead>
              <tr>
                <th>演练编号</th><th>演练名称</th><th>所属版本</th><th>事故类别</th>
                <th>演练日期</th><th>参演人数</th><th>结论评级</th><th>待整改</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="drill in plan.drills" :key="drill.id">                <td>{{ drill.演练编号 }}</td>
                <td>{{ drill.演练名称 }}</td>
                <td>{{ drill.版本号 }}</td>
                <td>{{ drill.事故类别 }}</td>
                <td>{{ drill.演练日期 }}</td>
                <td>{{ drill.参演人员.length }}</td>
                <td>{{ drill.演练结论评级 }}</td>
                <td>{{ drill.待整改数 }}</td>
              </tr>
              <tr v-if="!plan.drills.length">
                <td colspan="8" class="empty-state">该预案暂无演练记录</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>

    <VersionEditor
      v-if="editor.open"
      :plan-id="planId"
      :version-id="editor.versionId"
      :initial="editor.initial"
      @close="editor.open = false"
      @saved="onVersionChanged"
    />

    <div v-if="approve.open" class="modal-mask" @click.self="approve.open = false">
      <div class="modal small-modal">
        <header class="modal-head"><h3>批复版本 {{ approve.versionNo }}</h3></header>
        <form class="modal-body" @submit.prevent="confirmApprove">
          <label class="form-item">
            <span>批复人 <em>*</em></span>
            <input v-model="approve.approver" placeholder="批复签发人" />
          </label>
          <label class="form-item">
            <span>发布日期 <em>*</em></span>
            <input v-model="approve.publishDate" type="date" />
          </label>
          <p class="modal-tip">批复后该版本立即成为各页面一致可见的唯一现行版本，原版本转为历史版本且内容冻结。</p>
          <p v-if="approve.error" class="error-text">{{ approve.error }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="approve.open = false">取消</button>
            <button class="btn primary" type="submit">确认批复</button>
          </div>
        </form>
      </div>
    </div>

    <VersionView v-if="viewing" :version="viewing" @close="viewing = null" />

    <DrillCreate
      v-if="showDrillCreate && plan"
      :plan="plan"
      @close="showDrillCreate = false"
      @saved="onDrillSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { deleteAction, getJson, postAction } from '../api'
import VersionEditor from './VersionEditor.vue'
import VersionView from './VersionView.vue'
import DrillCreate from './DrillCreate.vue'

type Coverage = { rate: number; covered_count: number; total_types: number }
type VersionRow = {
  id: number
  版本号: string
  status: string
  is_current: boolean
  发布日期: string | null
  批复人: string | null
  事故类别: string[]
  演练场次: number
  coverage_year: Coverage
  coverage_all: Coverage
}
type PlanDetail = {
  id: number
  预案编号: string
  预案名称: string
  电站: string
  current_version: { 版本号: string; 发布日期: string } | null
  versions: VersionRow[]
  drills: DrillRow[]
}
type DrillRow = {
  id: number
  演练编号: string
  演练名称: string
  版本号: string
  事故类别: string
  演练日期: string
  参演人员: unknown[]
  演练结论评级: string
  待整改数: number
}

const props = defineProps<{ planId: number; year: number }>()
const emit = defineEmits<{
  close: []
  changed: []
  message: [message: string, ok?: boolean]
}>()

const plan = ref<PlanDetail | null>(null)
const editor = reactive({
  open: false,
  versionId: null as number | null,
  initial: null as Record<string, unknown> | null,
})
const viewing = ref<Record<string, any> | null>(null)
const showDrillCreate = ref(false)
const approve = reactive<{
  open: boolean
  versionId: number
  versionNo: string
  approver: string
  publishDate: string
  error: string
}>({
  open: false,
  versionId: 0,
  versionNo: '',
  approver: '',
  publishDate: new Date().toISOString().slice(0, 10),
  error: '',
})

function coverageClass(rate: number) {
  if (rate >= 100) return 'cov-full'
  if (rate >= 60) return 'cov-mid'
  return 'cov-low'
}

async function load() {
  plan.value = await getJson<PlanDetail>(`/${props.planId}?year=${props.year}`)
}

function startCreateVersion() {
  editor.open = true
  editor.versionId = null
  editor.initial = null
}

function editVersion(version: VersionRow) {
  editor.open = true
  editor.versionId = version.id
  editor.initial = { ...version }
}

function openApprove(version: VersionRow) {
  approve.open = true
  approve.versionId = version.id
  approve.versionNo = version.版本号
  approve.approver = ''
  approve.error = ''
}

async function act(versionId: number, action: string) {
  const result = await postAction(`/versions/${versionId}/actions`, { action })
  if (!result.ok) {
    emit('message', result.message, false)
    return
  }
  emit('message', result.message)
  await load()
  emit('changed')
}

async function confirmApprove() {
  approve.error = ''
  const result = await postAction(`/versions/${approve.versionId}/actions`, {
    action: '批复',
    批复人: approve.approver,
    发布日期: approve.publishDate,
  })
  if (!result.ok) {
    approve.error = result.message
    return
  }
  approve.open = false
  emit('message', result.message)
  await load()
  emit('changed')
}

async function discard(versionId: number) {
  if (!window.confirm('作废后该草稿不可恢复，确认作废？')) return
  const result = await deleteAction(`/versions/${versionId}`)
  emit('message', result.message, result.ok)
  if (result.ok) {
    await load()
    emit('changed')
  }
}

async function viewVersion(version: VersionRow) {
  viewing.value = await getJson(`/versions/${version.id}`)
}

function onVersionChanged(message: string) {
  editor.open = false
  emit('message', message)
  void load()
  emit('changed')
}

function onDrillSaved(message: string) {
  showDrillCreate.value = false
  emit('message', message)
  void load()
  emit('changed')
}

onMounted(load)
</script>

<style scoped>
.current {
  background: #f0f7ff;
}
.tag {
  display: inline-block;
  font-size: 11px;
  padding: 0 6px;
  border-radius: 4px;
  margin-left: 4px;
}
.tag-current {
  background: #1f6feb;
  color: #fff;
}
.cov-full { color: #067647; }
.cov-mid { color: #b54708; }
.cov-low { color: #b42318; }
.danger { color: #b42318; }
.detail-section {
  margin-bottom: 20px;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-head h4 {
  margin: 8px 0;
  font-size: 14px;
}
.small {
  padding: 4px 10px;
  font-size: 12px;
}
</style>
