<template>
  <section class="page" data-module="emergency_plan">
    <header class="page-head">
      <div>
        <h2>应急预案演练台账</h2>
        <p class="page-desc">
          预案改一版存一版，已批复版本只读；演练挂在具体版本下，覆盖率按当前版本实时重算，
          历史演练沿用旧版本口径归档。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="openPlanCreate">新建预案</button>
        <button class="btn primary" type="button" @click="switchTab('import')">导入预案</button>
      </div>
    </header>

    <p v-if="message" class="banner" :class="messageOk ? 'ok' : 'error-text'">{{ message }}</p>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="tab"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- 预案台账 -->
    <div v-if="activeTab === 'plans'">
      <form class="filter-bar" @submit.prevent="loadPlans">
        <label class="filter-item">
          <span>预案编号/名称</span>
          <input v-model="planFilter.keyword" placeholder="按编号或名称检索" />
        </label>
        <label class="filter-item">
          <span>电站</span>
          <input v-model="planFilter.station" placeholder="按电站过滤" />
        </label>
        <button class="btn" type="submit">查询</button>
      </form>
      <table class="data-table">
        <thead>
          <tr>
            <th>电站</th><th>预案编号</th><th>预案名称</th><th>当前版本</th>
            <th>{{ currentYear }} 年事故类别覆盖</th><th>覆盖率</th><th>版本数</th><th>待整改</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in planRows" :key="row.id">
            <td>{{ row.station }}</td>
            <td>{{ row.plan_code }}</td>
            <td>{{ row.plan_name }}</td>
            <td>
              <span v-if="row.current_version_no" class="badge current">{{ row.current_version_no }}</span>
              <span v-else class="muted">尚未批复版本</span>
            </td>
            <td class="type-cell">
              <span
                v-for="t in row.total_types"
                :key="t"
                class="chip"
                :class="{ covered: coveredSet(row).has(typeLabel(row, t)) }"
              >{{ typeLabel(row, t) }}</span>
            </td>
            <td>
              <span v-if="row.coverage_rate !== null" class="rate" :class="rateClass(row.coverage_rate)">
                {{ (row.coverage_rate * 100).toFixed(0) }}%
              </span>
              <span v-else class="muted">—</span>
            </td>
            <td>{{ row.version_count }}</td>
            <td>
              <span :class="row.rectifications_open ? 'error-text' : ''">{{ row.rectifications_open }}</span>
            </td>
            <td class="row-actions">
              <button class="link" type="button" @click="openPlanDetail(row.id)">版本与演练</button>
            </td>
          </tr>
          <tr v-if="!planRows.length">
            <td colspan="9" class="empty-state">暂无预案，可先新建预案或导入存量预案</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 预案详情：版本时间线 -->
    <div v-else-if="activeTab === 'detail' && planDetail">
      <button class="btn ghost" type="button" @click="switchTab('plans')">← 返回预案台账</button>
      <h3 class="detail-title">
        {{ planDetail.plan_name }}
        <span class="muted">{{ planDetail.plan_code }} · {{ planDetail.station }}</span>
      </h3>
      <div class="detail-summary">
        <span>当前版本：<b>{{ planDetail.current_version_no ?? '—' }}</b></span>
        <span>{{ currentYear }} 年演练：{{ planDetail.drills_this_year }} 场（累计 {{ planDetail.drills_total }} 场）</span>
        <span>待整改：<b :class="planDetail.rectifications_open ? 'error-text' : ''">{{ planDetail.rectifications_open }}</b> 项</span>
        <button class="btn primary" type="button" @click="openVersionCreate">新建版本（改一版存一版）</button>
      </div>

      <div v-if="versionForm.show" class="form-panel">
        <h4>{{ versionForm.id ? '编辑草稿版本' : '新建草稿版本' }}</h4>
        <div class="form-grid">
          <label><span>版本号 *</span><input v-model="versionForm.version_no" placeholder="如 V3.0" :disabled="!!versionForm.id" /></label>
          <label><span>发布日期</span><input v-model="versionForm.publish_date" type="date" /></label>
          <label class="full"><span>事故类别（逗号分隔）*</span>
            <input v-model="versionForm.typesText" placeholder="触电事故,直流拉弧火灾,极端天气" />
          </label>
          <label class="full"><span>修订摘要 *</span><textarea v-model="versionForm.content_summary" rows="2" /></label>
        </div>
        <div class="form-actions">
          <button class="btn primary" type="button" @click="saveVersion">保存</button>
          <button class="btn ghost" type="button" @click="versionForm.show = false">取消</button>
        </div>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>版本号</th><th>状态</th><th>事故类别</th><th>发布日期</th><th>批复人</th>
            <th>来源</th><th>演练(今年/累计)</th><th>本版覆盖率</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in planDetail.versions" :key="v.id" :class="{ 'row-current': v.is_current }">
            <td>
              {{ v.version_no }}
              <span v-if="v.is_current" class="badge current">当前</span>
            </td>
            <td><span class="badge" :class="statusClass(v.status)">{{ v.status }}</span></td>
            <td class="type-cell">
              <span v-for="t in v.accident_types" :key="t" class="chip">{{ t }}</span>
            </td>
            <td>{{ v.publish_date || '—' }}</td>
            <td>{{ v.approved_by || '—' }}</td>
            <td>{{ v.source }}</td>
            <td>{{ v.drill_count_this_year }} / {{ v.drill_count }}</td>
            <td>
              <span v-if="v.coverage_rate !== null" class="rate" :class="rateClass(v.coverage_rate)">
                {{ (v.coverage_rate * 100).toFixed(0) }}%
              </span>
              <span v-else class="muted">—</span>
            </td>
            <td class="row-actions">
              <button v-if="v.status === '草稿'" class="link" type="button" @click="openVersionEdit(v)">编辑</button>
              <button v-if="v.status === '草稿'" class="link" type="button" @click="versionAction(v.id, '提交批复')">提交批复</button>
              <button v-if="v.status === '待批复'" class="link" type="button" @click="versionAction(v.id, '批复通过')">批复通过</button>
              <button v-if="v.status === '待批复'" class="link" type="button" @click="versionAction(v.id, '批复驳回')">批复驳回</button>
              <button
                v-if="v.status === '已批复' || v.status === '已归档'"
                class="link"
                type="button"
                @click="openDrillCreate(v)"
              >登记演练</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="hint">已批复、已归档版本只读：换版必须新建版本，批复通过后旧版自动归档、当前版本指针整体切换。</p>
    </div>

    <!-- 演练记录 -->
    <div v-else-if="activeTab === 'drills'">
      <form class="filter-bar" @submit.prevent="loadDrills">
        <label class="filter-item"><span>年份</span><input v-model="drillFilter.year" placeholder="如 2026" /></label>
        <label class="filter-item"><span>预案</span>
          <select v-model="drillFilter.plan_id">
            <option value="">全部</option>
            <option v-for="p in allPlans" :key="p.id" :value="p.id">{{ p.plan_name }}</option>
          </select>
        </label>
        <label class="filter-item"><span>事故类别</span><input v-model="drillFilter.accident_type" placeholder="按事故类别" /></label>
        <button class="btn" type="submit">查询</button>
        <button class="btn primary" type="button" @click="openDrillCreate(null)">登记演练</button>
      </form>

      <div v-if="drillForm.show" class="form-panel">
        <h4>登记演练（{{ drillForm.versionLabel || '先选择预案版本' }}）</h4>
        <div class="form-grid">
          <label><span>预案 *</span>
            <select v-model="drillForm.plan_id" @change="onDrillPlanChange">
              <option value="">请选择</option>
              <option v-for="p in allPlans" :key="p.id" :value="p.id">{{ p.plan_name }}</option>
            </select>
          </label>
          <label><span>预案版本 *</span>
            <select v-model="drillForm.version_id" @change="onDrillVersionChange">
              <option value="">请选择</option>
              <option v-for="v in drillForm.versionOptions" :key="v.id" :value="v.id">
                {{ v.version_no }}（{{ v.status }}）
              </option>
            </select>
          </label>
          <label><span>演练编号 *</span><input v-model="drillForm.drill_no" placeholder="如 YL-2026-010" /></label>
          <label><span>演练日期 *</span><input v-model="drillForm.drill_date" type="date" /></label>
          <label><span>事故类别 *</span>
            <select v-model="drillForm.accident_type">
              <option value="">请选择</option>
              <option v-for="t in drillForm.typeOptions" :key="t" :value="t">{{ t }}</option>
            </select>
          </label>
          <label class="full"><span>参演人员（逐条添加）*</span>
            <span class="inline-add">
              <input v-model="drillForm.personInput" placeholder="输入姓名后回车或点添加" @keyup.enter.prevent="addParticipant" />
              <button class="btn" type="button" @click="addParticipant">添加</button>
            </span>
            <span class="chip removable" v-for="(name, idx) in drillForm.participants" :key="idx">
              {{ name }}<button type="button" @click="drillForm.participants.splice(idx, 1)">×</button>
            </span>
          </label>
          <label class="full"><span>演练结论 *</span><textarea v-model="drillForm.conclusion" rows="2" /></label>
        </div>
        <div class="form-actions">
          <button class="btn primary" type="button" @click="saveDrill">保存演练记录</button>
          <button class="btn ghost" type="button" @click="drillForm.show = false">取消</button>
        </div>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>演练编号</th><th>预案</th><th>版本</th><th>演练日期</th><th>事故类别</th>
            <th>参演人员</th><th>演练结论</th><th>未闭环整改</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in drillRows" :key="row.id">
            <td>{{ row.drill_no }}</td>
            <td>{{ row.plan_name }}</td>
            <td><span class="badge" :class="statusClass(row.version_status)">{{ row.version_no }}</span></td>
            <td>{{ row.drill_date }}</td>
            <td>{{ row.accident_type }}</td>
            <td>{{ row.participants.join('、') }}</td>
            <td class="conclusion">{{ row.conclusion }}</td>
            <td :class="row.rectification_open ? 'error-text' : ''">{{ row.rectification_open }}</td>
            <td class="row-actions"><button class="link" type="button" @click="openDrillDetail(row.id)">整改项</button></td>
          </tr>
          <tr v-if="!drillRows.length">
            <td colspan="9" class="empty-state">暂无演练记录</td>
          </tr>
        </tbody>
      </table>

      <div v-if="drillDetail" class="drawer">
        <div class="drawer-head">
          <h4>{{ drillDetail.drill_no }} · {{ drillDetail.accident_type }}（{{ drillDetail.drill_date }}）</h4>
          <button class="btn ghost" type="button" @click="drillDetail = null">关闭</button>
        </div>
        <p class="muted">参演：{{ drillDetail.participants.join('、') }} ｜ 结论：{{ drillDetail.conclusion }}</p>
        <table class="data-table">
          <thead><tr><th>整改内容</th><th>责任人</th><th>时限</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="r in drillDetail.rectifications" :key="r.id">
              <td>{{ r.content }}</td><td>{{ r.assignee || '—' }}</td><td>{{ r.due_date || '—' }}</td>
              <td><span class="badge" :class="rectClass(r.status)">{{ r.status }}</span></td>
              <td class="row-actions">
                <button v-if="r.status === '待整改'" class="link" type="button" @click="rectAction(r.id, '开始整改')">开始整改</button>
                <button v-if="r.status === '整改中'" class="link" type="button" @click="rectAction(r.id, '闭环验证')">闭环验证</button>
              </td>
            </tr>
            <tr v-if="!drillDetail.rectifications.length"><td colspan="5" class="empty-state">该次演练暂无整改项</td></tr>
          </tbody>
        </table>
        <div class="form-grid compact">
          <label class="full"><span>新增整改项 *</span><input v-model="rectForm.content" placeholder="演练发现的问题与整改要求" /></label>
          <label><span>责任人</span><input v-model="rectForm.assignee" /></label>
          <label><span>整改时限</span><input v-model="rectForm.due_date" type="date" /></label>
          <button class="btn primary" type="button" @click="saveRectification">落入演练待办</button>
        </div>
      </div>
    </div>

    <!-- 演练待办 -->
    <div v-else-if="activeTab === 'todos'">
      <form class="filter-bar" @submit.prevent="loadRectifications">
        <label class="filter-item"><span>状态</span>
          <select v-model="rectFilter.status">
            <option value="">全部</option>
            <option v-for="s in rectStatuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <label class="filter-item"><span>责任人</span><input v-model="rectFilter.assignee" /></label>
        <button class="btn" type="submit">查询</button>
      </form>
      <table class="data-table">
        <thead>
          <tr><th>整改内容</th><th>来源演练</th><th>预案</th><th>责任人</th><th>时限</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rectRows" :key="r.id">
            <td>{{ r.content }}</td>
            <td>{{ r.drill_no }}（{{ r.drill_date }} · {{ r.accident_type }}）</td>
            <td>{{ r.plan_name }}</td>
            <td>{{ r.assignee || '—' }}</td>
            <td>{{ r.due_date || '—' }}</td>
            <td><span class="badge" :class="rectClass(r.status)">{{ r.status }}</span></td>
            <td class="row-actions">
              <button v-if="r.status === '待整改'" class="link" type="button" @click="rectAction(r.id, '开始整改', true)">开始整改</button>
              <button v-if="r.status === '整改中'" class="link" type="button" @click="rectAction(r.id, '闭环验证', true)">闭环验证</button>
            </td>
          </tr>
          <tr v-if="!rectRows.length"><td colspan="7" class="empty-state">暂无演练整改待办</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 导入记录 -->
    <div v-else-if="activeTab === 'import'">
      <div class="form-panel">
        <h4>导入预案版本</h4>
        <p class="hint">同一份预案按「预案编号 + 版本号」去重，重复行只留一条；每次导入（含重复行）都会生成导入记录。</p>
        <div class="form-grid">
          <label><span>导入口径</span>
            <select v-model="importForm.import_type">
              <option value="增量导入">增量导入（新进版本为草稿，批复后生效）</option>
              <option value="存量回填">存量回填（按发布日期定为已批复，最近一版为当前版本）</option>
            </select>
          </label>
          <label><span>操作人</span><input v-model="importForm.operator" /></label>
          <label class="full"><span>备注</span><input v-model="importForm.remark" /></label>
        </div>
        <table class="data-table inner-table">
          <thead>
            <tr>
              <th>预案编号 *</th><th>预案名称</th><th>电站</th><th>版本号 *</th>
              <th>事故类别（逗号分隔）</th><th>发布日期</th><th>批复人</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in importForm.rows" :key="idx">
              <td><input v-model="row.plan_code" /></td>
              <td><input v-model="row.plan_name" /></td>
              <td><input v-model="row.station" /></td>
              <td><input v-model="row.version_no" /></td>
              <td><input v-model="row.accident_types" /></td>
              <td><input v-model="row.publish_date" type="date" /></td>
              <td><input v-model="row.approved_by" /></td>
              <td><button class="link" type="button" @click="importForm.rows.splice(idx, 1)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <div class="form-actions">
          <button class="btn" type="button" @click="importForm.rows.push(blankImportRow())">添加一行</button>
          <button class="btn primary" type="button" @click="submitImport">开始导入</button>
        </div>
      </div>

      <h3 class="detail-title">历史导入记录</h3>
      <table class="data-table">
        <thead>
          <tr><th>批次号</th><th>口径</th><th>操作人</th><th>总行数</th><th>新增</th><th>重复</th><th>时间</th><th>备注</th><th>明细</th></tr>
        </thead>
        <tbody>
          <tr v-for="b in importBatches" :key="b.id">
            <td>{{ b.batch_no }}</td>
            <td>{{ b.import_type }}</td>
            <td>{{ b.operator }}</td>
            <td>{{ b.total_rows }}</td>
            <td>{{ b.created_count }}</td>
            <td :class="b.duplicated_count ? 'error-text' : ''">{{ b.duplicated_count }}</td>
            <td>{{ b.created_at }}</td>
            <td>{{ b.remark || '—' }}</td>
            <td>
              <button class="link" type="button" @click="expandedImport = expandedImport === b.id ? null : b.id">
                {{ expandedImport === b.id ? '收起' : '查看逐行结果' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <table v-if="expandedImport" class="data-table inner-table">
        <thead><tr><th>行号</th><th>预案编号</th><th>版本号</th><th>结果</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="d in expandedBatch?.details" :key="d.row_no">
            <td>{{ d.row_no }}</td><td>{{ d.plan_code }}</td><td>{{ d.version_no }}</td>
            <td><span class="badge" :class="d.result === '新增' ? 'status-approved' : d.result === '重复' ? 'status-archived' : 'status-draft'">{{ d.result }}</span></td>
            <td>{{ d.message }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 新建预案 -->
    <div v-if="planCreateShow" class="modal-mask" @click.self="planCreateShow = false">
      <div class="modal">
        <h4>新建预案</h4>
        <div class="form-grid">
          <label class="full"><span>预案编号 *</span><input v-model="planCreate.plan_code" placeholder="如 YJYA-GF-04" /></label>
          <label class="full"><span>预案名称 *</span><input v-model="planCreate.plan_name" /></label>
          <label class="full"><span>所属电站 *</span><input v-model="planCreate.station" /></label>
        </div>
        <div class="form-actions">
          <button class="btn primary" type="button" @click="savePlan">保存并去建版本</button>
          <button class="btn ghost" type="button" @click="planCreateShow = false">取消</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const API = '/api/emergency-plans'

type CoverageItem = {
  id: number
  plan_id: number
  plan_code: string
  plan_name: string
  station: string
  current_version_no: string | null
  year: number
  total_types: number
  covered_types: number
  coverage_rate: number | null
  accident_types: string[]
  covered_accident_types: string[]
  version_count: number
  rectifications_open: number
}

type PlanVersion = {
  id: number
  version_no: string
  status: string
  accident_types: string[]
  publish_date: string
  approved_by: string
  content_summary: string
  source: string
  is_current: boolean
  drill_count: number
  drill_count_this_year: number
  coverage_rate: number | null
}

const tabs = [
  { key: 'plans', label: '预案台账' },
  { key: 'drills', label: '演练记录' },
  { key: 'todos', label: '演练待办' },
  { key: 'import', label: '导入记录' },
]

const activeTab = ref('plans')
const message = ref('')
const messageOk = ref(true)
const currentYear = new Date().getFullYear()

const planRows = ref<CoverageItem[]>([])
const allPlans = ref<CoverageItem[]>([])
// versionId -> planId 的映射，从版本按钮登记演练时用来反查所属预案。
const versionPlanMap = ref<Map<number, number>>(new Map())
const planDetail = ref<(Record<string, unknown> & { versions: PlanVersion[] }) | null>(null)
const drillRows = ref<Record<string, any>[]>([])
const rectRows = ref<Record<string, any>[]>([])
const importBatches = ref<Record<string, any>[]>([])
const expandedImport = ref<number | null>(null)
const drillDetail = ref<Record<string, any> | null>(null)
const planCreateShow = ref(false)

const planFilter = reactive({ keyword: '', station: '' })
const drillFilter = reactive({ year: String(currentYear), plan_id: '', accident_type: '' })
const rectFilter = reactive({ status: '', assignee: '' })
const rectStatuses = ['待整改', '整改中', '已闭环']

const stats = ref([
  { label: '在册预案', value: '—' },
  { label: `${currentYear} 年平均覆盖率`, value: '—' },
  { label: `${currentYear} 年演练场次`, value: '—' },
  { label: '待整改项', value: '—' },
])

function flash(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

async function postJson(path: string, body: unknown): Promise<any> {
  const res = await request(path, { method: 'POST', body: JSON.stringify(body) })
  return res.json()
}

async function putJson(path: string, body: unknown): Promise<any> {
  const res = await request(path, { method: 'PUT', body: JSON.stringify(body) })
  return res.json()
}

// ---------------------------------------------------------------- 覆盖率/预案
async function loadPlans() {
  const qs = new URLSearchParams()
  if (planFilter.keyword) qs.set('keyword', planFilter.keyword)
  if (planFilter.station) qs.set('station', planFilter.station)
  qs.set('size', '200')
  const res = await request(`${API}?${qs}`)
  const data = await res.json()
  planRows.value = data.items ?? []
}

async function loadCoverage() {
  const res = await request(`${API}/coverage`)
  const data = await res.json()
  // 覆盖率接口主键叫 plan_id，列表接口叫 id：统一补别名，页面只按 id 用。
  const items = (data.items ?? []).map((p: Record<string, unknown> & { plan_id: number }) => ({
    ...p,
    id: p.plan_id,
  })) as CoverageItem[]
  allPlans.value = items
  if (activeTab.value === 'plans') planRows.value = items
  const totalRect = items.reduce((sum, p) => sum + p.rectifications_open, 0)
  stats.value[0].value = String(items.length)
  stats.value[1].value = data.overall_rate === null ? '—' : `${(data.overall_rate * 100).toFixed(0)}%`
  const drillRes = await request(`${API}/drills/list?year=${currentYear}&size=200`)
  const drillData = await drillRes.json()
  stats.value[2].value = String(drillData.total ?? 0)
  stats.value[3].value = String(totalRect)
}

function coveredSet(row: CoverageItem) {
  return new Set(row.covered_accident_types)
}

// 覆盖率看板行本身已带 accident_types；typeLabel 直接按列序回显。
function typeLabel(row: CoverageItem, index: number) {
  return row.accident_types[index - 1] ?? ''
}

function rateClass(rate: number) {
  if (rate >= 0.8) return 'rate-high'
  if (rate >= 0.5) return 'rate-mid'
  return 'rate-low'
}

function statusClass(status: string) {
  return {
    草稿: 'status-draft',
    待批复: 'status-pending',
    已批复: 'status-approved',
    已归档: 'status-archived',
  }[status] ?? 'status-draft'
}

function rectClass(status: string) {
  return {
    待整改: 'status-pending',
    整改中: 'status-draft',
    已闭环: 'status-approved',
  }[status] ?? 'status-draft'
}

// ---------------------------------------------------------------- 新建预案
const planCreate = reactive({ plan_code: '', plan_name: '', station: '' })
function openPlanCreate() {
  planCreate.plan_code = planCreate.plan_name = planCreate.station = ''
  planCreateShow.value = true
}

async function savePlan() {
  const r = await postJson(API, { ...planCreate })
  if (!r.ok) { flash(r.message, false); return }
  planCreateShow.value = false
  flash('预案已建立，请继续新建第一个版本')
  await openPlanDetail(r.entry.id)
  openVersionCreate()
  await loadCoverage()
}

// ---------------------------------------------------------------- 版本管理
async function openPlanDetail(planId: number) {
  const res = await request(`${API}/${planId}`)
  planDetail.value = await res.json()
  activeTab.value = 'detail'
}

const blankVersion = () => ({
  show: false, id: null as number | null, version_no: '', publish_date: '',
  typesText: '', content_summary: '',
})
const versionForm = reactive(blankVersion())

function openVersionCreate() {
  Object.assign(versionForm, blankVersion(), { show: true })
}

function openVersionEdit(v: PlanVersion) {
  Object.assign(versionForm, {
    show: true,
    id: v.id,
    version_no: v.version_no,
    publish_date: v.publish_date,
    typesText: v.accident_types.join(','),
    content_summary: v.content_summary,
  })
}

async function saveVersion() {
  if (!planDetail.value) return
  const payload = {
    version_no: versionForm.version_no,
    publish_date: versionForm.publish_date,
    accident_types: versionForm.typesText,
    content_summary: versionForm.content_summary,
  }
  const r = versionForm.id
    ? await putJson(`${API}/versions/${versionForm.id}`, payload)
    : await postJson(`${API}/${planDetail.value.id}/versions`, payload)
  if (!r.ok) { flash(r.message, false); return }
  flash(r.message)
  versionForm.show = false
  await openPlanDetail(planDetail.value.id as number)
  await loadCoverage()
}

async function versionAction(versionId: number, action: string) {
  const r = await postJson(`${API}/versions/${versionId}/actions`, { action })
  if (!r.ok) { flash(r.message, false); return }
  flash(r.message)
  if (planDetail.value) await openPlanDetail(planDetail.value.id as number)
  await loadCoverage()
}

// ---------------------------------------------------------------- 演练
async function loadDrills() {
  const qs = new URLSearchParams()
  if (drillFilter.year) qs.set('year', drillFilter.year)
  if (drillFilter.plan_id) qs.set('plan_id', drillFilter.plan_id)
  if (drillFilter.accident_type) qs.set('accident_type', drillFilter.accident_type)
  qs.set('size', '200')
  const res = await request(`${API}/drills/list?${qs}`)
  const data = await res.json()
  drillRows.value = data.items ?? []
}

const drillForm = reactive({
  show: false,
  plan_id: '' as number | '',
  version_id: '' as number | '',
  versionOptions: [] as PlanVersion[],
  typeOptions: [] as string[],
  versionLabel: '',
  drill_no: '',
  drill_date: '',
  accident_type: '',
  personInput: '',
  participants: [] as string[],
  conclusion: '',
})

function resetDrillForm() {
  Object.assign(drillForm, {
    show: true, plan_id: '', version_id: '', versionOptions: [], typeOptions: [],
    versionLabel: '', drill_no: '', drill_date: '', accident_type: '',
    personInput: '', participants: [], conclusion: '',
  })
}

async function openDrillCreate(version: PlanVersion | null) {
  resetDrillForm()
  await loadCoverage()
  if (version) {
    await ensureVersionPlanMap()
    drillForm.plan_id = versionPlanMap.value.get(version.id) ?? ''
    await onDrillPlanChange()
    drillForm.version_id = version.id
    await onDrillVersionChange()
  }
}

// 拉取各预案版本列表，建立 版本->预案 反查表（并发一次，不逐条点查）。
async function ensureVersionPlanMap() {
  if (versionPlanMap.value.size) return
  const lists = await Promise.all(
    allPlans.value.map(async (p) => {
      const res = await request(`${API}/${p.plan_id}/versions`)
      const data = await res.json()
      return { planId: p.plan_id, items: data.items as PlanVersion[] }
    }),
  )
  const map = new Map<number, number>()
  for (const { planId, items } of lists) {
    for (const v of items) map.set(v.id, planId)
  }
  versionPlanMap.value = map
}

async function onDrillPlanChange() {
  drillForm.version_id = ''
  drillForm.typeOptions = []
  drillForm.versionLabel = ''
  if (!drillForm.plan_id) { drillForm.versionOptions = []; return }
  const res = await request(`${API}/${drillForm.plan_id}/versions`)
  const data = await res.json()
  drillForm.versionOptions = data.items ?? []
}

async function onDrillVersionChange() {
  const v = drillForm.versionOptions.find((item) => item.id === drillForm.version_id)
  drillForm.typeOptions = v ? v.accident_types : []
  drillForm.accident_type = ''
  drillForm.versionLabel = v ? `${v.version_no}（${v.status}）` : ''
}

function addParticipant() {
  const name = drillForm.personInput.trim()
  if (name && !drillForm.participants.includes(name)) drillForm.participants.push(name)
  drillForm.personInput = ''
}

async function saveDrill() {
  const r = await postJson(`${API}/drills`, {
    version_id: drillForm.version_id,
    drill_no: drillForm.drill_no,
    drill_date: drillForm.drill_date,
    accident_type: drillForm.accident_type,
    participants: drillForm.participants,
    conclusion: drillForm.conclusion,
  })
  if (!r.ok) { flash(r.message, false); return }
  flash('演练记录已登记')
  drillForm.show = false
  await loadDrills()
  await loadCoverage()
}

async function openDrillDetail(drillId: number) {
  const res = await request(`${API}/drills/${drillId}`)
  drillDetail.value = await res.json()
  rectForm.content = ''
  rectForm.assignee = ''
  rectForm.due_date = ''
}

const rectForm = reactive({ content: '', assignee: '', due_date: '' })

async function saveRectification() {
  if (!drillDetail.value || !rectForm.content) { flash('整改内容不能为空', false); return }
  const r = await postJson(`${API}/drills/${drillDetail.value.id}/rectifications`, { ...rectForm })
  if (!r.ok) { flash(r.message, false); return }
  flash(r.message)
  await openDrillDetail(drillDetail.value.id as number)
  await loadCoverage()
}

async function rectAction(rectId: number, action: string, fromTodo = false) {
  const r = await postJson(`${API}/rectifications/${rectId}/actions`, { action })
  if (!r.ok) { flash(r.message, false); return }
  flash(r.message)
  if (fromTodo) await loadRectifications()
  if (drillDetail.value) await openDrillDetail(drillDetail.value.id as number)
  await loadCoverage()
}

// ---------------------------------------------------------------- 待办
async function loadRectifications() {
  const qs = new URLSearchParams()
  if (rectFilter.status) qs.set('status', rectFilter.status)
  if (rectFilter.assignee) qs.set('assignee', rectFilter.assignee)
  const res = await request(`${API}/rectifications?${qs}`)
  const data = await res.json()
  rectRows.value = data.items ?? []
}

// ---------------------------------------------------------------- 导入
function blankImportRow() {
  return { plan_code: '', plan_name: '', station: '', version_no: '', accident_types: '', publish_date: '', approved_by: '' }
}

const importForm = reactive({
  import_type: '增量导入',
  operator: '',
  remark: '',
  rows: [blankImportRow()],
})

async function loadImports() {
  const res = await request(`${API}/imports/list`)
  const data = await res.json()
  importBatches.value = data.items ?? []
}

const expandedBatch = computed(() => importBatches.value.find((b) => b.id === expandedImport.value) ?? null)

async function submitImport() {
  const rows = importForm.rows.filter((r) => r.plan_code && r.version_no)
  if (!rows.length) { flash('至少填写一行（预案编号、版本号必填）', false); return }
  const r = await postJson(`${API}/imports`, {
    import_type: importForm.import_type,
    operator: importForm.operator,
    remark: importForm.remark,
    rows,
  })
  if (!r.ok) { flash(r.message, false); return }
  flash(r.message)
  importForm.rows = [blankImportRow()]
  await loadImports()
  await loadCoverage()
}

async function switchTab(key: string) {
  activeTab.value = key
  message.value = ''
  if (key === 'plans') await loadCoverage()
  if (key === 'drills') await loadDrills()
  if (key === 'todos') await loadRectifications()
  if (key === 'import') await loadImports()
}

onMounted(async () => {
  await loadCoverage()
  await loadPlans()
})
</script>

<style scoped>
.muted { color: var(--muted); }
.banner { padding: 8px 12px; border-radius: 6px; background: #ecfdf3; color: #027a48; font-size: 13px; }
.banner.error-text { background: #fef3f2; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
.tab { border: none; background: none; padding: 8px 16px; cursor: pointer; font-size: 14px; color: var(--muted); border-bottom: 2px solid transparent; }
.tab.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; }
.badge.current { background: var(--brand); color: #fff; }
.status-draft { background: #f2f4f7; color: #475467; }
.status-pending { background: #fffaeb; color: #b54708; }
.status-approved { background: #ecfdf3; color: #027a48; }
.status-archived { background: #eef2f6; color: #667085; }
.chip { display: inline-block; margin: 1px 4px 1px 0; padding: 1px 8px; border-radius: 10px; background: #f2f4f7; color: #98a2b3; font-size: 12px; }
.chip.covered { background: #ecfdf3; color: #027a48; }
.chip.removable button { border: none; background: none; cursor: pointer; margin-left: 4px; color: var(--muted); }
.rate { font-weight: 600; }
.rate-high { color: #027a48; }
.rate-mid { color: #b54708; }
.rate-low { color: #b42318; }
.type-cell { max-width: 260px; }
.detail-title { margin: 14px 0 8px; font-size: 16px; display: flex; gap: 10px; align-items: baseline; }
.detail-summary { display: flex; gap: 20px; align-items: center; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; font-size: 13px; }
.row-current { background: #f5f9ff; }
.hint { color: var(--muted); font-size: 12px; margin-top: 8px; }
.form-panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; }
.form-panel h4 { margin: 0 0 10px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
.form-grid.compact { grid-template-columns: 2fr 1fr 1fr auto; align-items: end; }
.form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-grid label.full { grid-column: 1 / -1; }
.form-grid input, .form-grid select, .form-grid textarea { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.form-actions { display: flex; gap: 8px; }
.inline-add { display: flex; gap: 6px; }
.conclusion { max-width: 220px; }
.inner-table { margin: 10px 0; font-size: 12px; }
.inner-table input { width: 100%; padding: 4px 6px; border: 1px solid var(--border); border-radius: 4px; }
.drawer { margin-top: 14px; background: #fff; border: 1px solid var(--brand); border-radius: 8px; padding: 12px 14px; }
.drawer-head { display: flex; justify-content: space-between; align-items: center; }
.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 460px; }
.modal input { width: 100%; padding: 7px 8px; border: 1px solid var(--border); border-radius: 6px; }
select, input, textarea { font-family: inherit; }
</style>
