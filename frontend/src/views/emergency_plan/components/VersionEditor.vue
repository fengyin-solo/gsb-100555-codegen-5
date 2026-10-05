<template>
  <div class="modal-mask" @click.self="$emit('close')">
    <div class="modal">
      <header class="modal-head">
        <h3>{{ versionId ? '编辑草稿版本' : '新建下一版草稿' }}</h3>
        <button class="link" type="button" @click="$emit('close')">关闭</button>
      </header>
      <form class="modal-body" @submit.prevent="submit">
        <p class="modal-tip">
          已批复版本不可修改，这里编辑的始终是草稿；事故类别决定该版本演练覆盖率的分母。
        </p>
        <label class="form-item">
          <span>版本号 <em>*</em></span>
          <input v-model="form.版本号" placeholder="如 C/0、V3.0" />
        </label>
        <fieldset class="form-item">
          <legend>覆盖事故类别 <em>*</em></legend>
          <div class="check-grid">
            <label v-for="item in catalog" :key="item" class="check-item">
              <input v-model="form.事故类别" type="checkbox" :value="item" />
              {{ item }}
            </label>
          </div>
          <div class="custom-type">
            <input v-model="customType" placeholder="补充目录之外的类别" />
            <button class="btn small" type="button" @click="addCustom">追加</button>
          </div>
        </fieldset>
        <label class="form-item">
          <span>预案内容 / 修订说明</span>
          <textarea v-model="form.预案内容" rows="5" placeholder="本版修订要点、处置卡变化等"></textarea>
        </label>
        <p v-if="error" class="error-text">{{ error }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="$emit('close')">取消</button>
          <button class="btn primary" type="submit">{{ versionId ? '保存草稿' : '建立草稿' }}</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { fetchMeta, postAction, putAction } from '../api'

const props = defineProps<{
  planId: number
  versionId: number | null
  initial: Record<string, unknown> | null
}>()
const emit = defineEmits<{ close: []; saved: [message: string] }>()

const catalog = ref<string[]>([])
const customType = ref('')
const error = ref('')
const form = reactive({ 版本号: '', 事故类别: [] as string[], 预案内容: '' })

onMounted(async () => {
  const meta = await fetchMeta()
  catalog.value = meta.accident_catalog
  if (props.initial) {
    form.版本号 = String(props.initial.版本号 ?? '')
    form.事故类别 = [...(props.initial.事故类别 as string[]) ?? []]
    form.预案内容 = String(props.initial.预案内容 ?? '')
  }
})

function addCustom() {
  const value = customType.value.trim()
  if (value && !form.事故类别.includes(value)) form.事故类别.push(value)
  customType.value = ''
}

async function submit() {
  error.value = ''
  if (!form.版本号.trim()) {
    error.value = '版本号必填'
    return
  }
  const body = { ...form }
  const result = props.versionId
    ? await putAction(`/versions/${props.versionId}`, body)
    : await postAction(`/${props.planId}/versions`, body)
  if (!result.ok) {
    error.value = result.message
    return
  }
  emit('saved', result.message)
}
</script>

<style scoped>
.check-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px 12px;
  margin: 6px 0;
}
.check-item {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.custom-type {
  display: flex;
  gap: 8px;
}
.custom-type input {
  flex: 1;
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
