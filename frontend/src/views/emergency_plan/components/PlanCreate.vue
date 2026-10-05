<template>
  <div class="modal-mask" @click.self="$emit('close')">
    <div class="modal">
      <header class="modal-head">
        <h3>登记预案主档</h3>
        <button class="link" type="button" @click="$emit('close')">关闭</button>
      </header>
      <p class="modal-tip">主档只登记“预案编号 + 预案名称 + 电站”，版本在详情里逐版建立与批复。</p>
      <form class="modal-body" @submit.prevent="submit">
        <label class="form-item">
          <span>预案编号 <em>*</em></span>
          <input v-model="form.预案编号" placeholder="如 YJYA-YG-01" />
        </label>
        <label class="form-item">
          <span>预案名称 <em>*</em></span>
          <input v-model="form.预案名称" placeholder="如 光伏场区综合应急预案" />
        </label>
        <label class="form-item">
          <span>所属电站 <em>*</em></span>
          <input v-model="form.电站" placeholder="如 羊岗光伏电站" />
        </label>
        <p v-if="error" class="error-text">{{ error }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="$emit('close')">取消</button>
          <button class="btn primary" type="submit">保存主档</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'

import { postAction } from '../api'

const emit = defineEmits<{ close: []; done: [message: string] }>()

const form = reactive({ 预案编号: '', 预案名称: '', 电站: '' })
const error = ref('')

async function submit() {
  error.value = ''
  const result = await postAction('', form)
  if (!result.ok) {
    error.value = result.message
    return
  }
  emit('done', '预案主档已登记，请在详情中建立首版草稿')
}
</script>
