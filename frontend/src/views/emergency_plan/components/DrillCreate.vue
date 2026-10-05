<template>
  <div class="modal-mask wide" @click.self="$emit('close')">
    <div class="modal">
      <header class="modal-head">
        <h3>登记演练记录</h3>
        <button class="link" type="button" @click="$emit('close')">关闭</button>
      </header>
      <form class="modal-body" @submit.prevent="submit">
        <p class="modal-tip">
          演练只能挂在<strong>已批复版本</strong>下；归档后即使预案换版，该记录仍沿用所挂版本的覆盖率口径。
        </p>
        <div class="form-grid">
          <label class="form-item">
            <span>所属版本 <em>*</em></span>
            <select v-model="form.version_id">
              <option :value="0" disabled>请选择已批复版本</option>
              <option v-for="version in approvedVersions" :key="Number(version.id)" :value="Number(version.id)">
                {{ version.版本号 }}（{{ version.status }}{{ version.is_current ? '·现行' : '' }}，{{ version.发布日期 }}）
              </option>
            </select>
          </label>
          <label class="form-item">
            <span>演练名称 <em>*</em></span>
            <input v-model="form.演练名称" placeholder="如 储能电池热失控处置演练" />
          </label>
          <label class="form-item">
            <span>演练日期 <em>*</em></span>
            <input v-model="form.演练日期" type="date" />
          </label>
          <label class="form-item">
            <span>事故类别 <em>*</em></span>
            <input v-model="form.事故类别" list="accident-catalog" placeholder="选择或输入" />
            <datalist id="accident-catalog">
              <option v-for="item in catalog" :key="item" :value="item" />
            </datalist>
          </label>
          <label class="form-item">
            <span>演练地点</span>
            <input v-model="form.演练地点" />
          </label>
          <label class="form-item">
            <span>总指挥</span>
            <input v-model="form.总指挥" />
          </label>
          <label class="form-item">
            <span>演练结论评级</span>
            <select v-model="form.演练结论评级">
              <option v-for="grade in grades" :key="grade" :value="grade">{{ grade }}</option>
            </select>
          </label>
        </div>

        <label class="form-item">
          <span>演练结论</span>
          <textarea v-model="form.演练结论" rows="3" placeholder="演练过程评价、存在的问题等"></textarea>
        </label>

        <section class="sub-block">
          <div class="section-head">
            <h4>参演人员（逐条录入）</h4>
            <button class="btn small" type="button" @click="addParticipant">添加人员</button>
          </div>
          <div v-for="(person, index) in form.参演人员" :key="index" class="inline-row">
            <input v-model="person.姓名" placeholder="姓名" />
            <input v-model="person.岗位" placeholder="岗位 / 角色" />
            <button class="link danger" type="button" @click="form.参演人员.splice(index, 1)">移除</button>
          </div>
          <p v-if="!form.参演人员.length" class="empty-state">尚未添加参演人员</p>
        </section>

        <section class="sub-block">
          <div class="section-head">
            <h4>整改项（保存后自动进入演练待办）</h4>
            <button class="btn small" type="button" @click="addRectification">添加整改项</button>
          </div>
          <div v-for="(item, index) in form.整改项" :key="index" class="inline-row rect-row">
            <input v-model="item.整改内容" placeholder="整改内容" />
            <input v-model="item.责任人" placeholder="责任人" class="narrow" />
            <input v-model="item.整改期限" type="date" class="narrow" />
            <button class="link danger" type="button" @click="form.整改项.splice(index, 1)">移除</button>
          </div>
          <p v-if="!form.整改项.length" class="empty-state">本次演练无整改项</p>
        </section>

        <p v-if="error" class="error-text">{{ error }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="$emit('close')">取消</button>
          <button class="btn primary" type="submit">保存演练记录</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { fetchMeta, postAction } from '../api'

const props = defineProps<{ plan: Record<string, any> }>()
const emit = defineEmits<{ close: []; saved: [message: string] }>()

const catalog = ref<string[]>([])
const grades = ref<string[]>([])
const error = ref('')
const today = new Date().toISOString().slice(0, 10)

const form = reactive({
  version_id: 0,
  演练名称: '',
  演练日期: today,
  事故类别: '',
  演练地点: '',
  总指挥: '',
  演练结论评级: '合格',
  演练结论: '',
  参演人员: [] as { 姓名: string; 岗位: string }[],
  整改项: [] as { 整改内容: string; 责任人: string; 整改期限: string }[],
})

const approvedVersions = computed<Record<string, any>[]>(() =>
  (props.plan.versions as Record<string, any>[]).filter(
    (item) => item.status === '已批复',
  ),
)

onMounted(async () => {
  const meta = await fetchMeta()
  catalog.value = meta.accident_catalog
  grades.value = meta.conclusion_grades
  const current = approvedVersions.value.find((item) => item.is_current)
  if (current) form.version_id = Number(current.id)
})

function addParticipant() {
  form.参演人员.push({ 姓名: '', 岗位: '' })
}

function addRectification() {
  form.整改项.push({ 整改内容: '', 责任人: '', 整改期限: '' })
}

async function submit() {
  error.value = ''
  if (!form.version_id) {
    error.value = '请选择演练所属的已批复版本'
    return
  }
  const result = await postAction('/drills', {
    plan_id: props.plan.id,
    ...form,
  })
  if (!result.ok) {
    error.value = result.message
    return
  }
  emit('saved', result.message)
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 16px;
}
.sub-block {
  margin-top: 14px;
  border-top: 1px dashed var(--border);
  padding-top: 8px;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-head h4 {
  margin: 6px 0;
  font-size: 13px;
}
.inline-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
.inline-row input {
  flex: 1;
}
.inline-row .narrow {
  flex: 0 0 130px;
}
.small {
  padding: 4px 10px;
  font-size: 12px;
}
.danger {
  color: #b42318;
  white-space: nowrap;
}
textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  font-family: inherit;
  font-size: 13px;
  resize: vertical;
}
</style>
