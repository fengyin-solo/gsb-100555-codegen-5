<template>
  <div class="modal-mask" @click.self="$emit('close')">
    <div class="modal">
      <header class="modal-head">
        <h3>版本 {{ version.版本号 }}（只读）</h3>
        <button class="link" type="button" @click="$emit('close')">关闭</button>
      </header>
      <div class="modal-body">
        <p class="modal-tip">
          {{ version.预案名称 }} ｜ {{ version.status }}
          <span v-if="version.is_current">｜现行版本</span>
          ｜发布 {{ version.发布日期 ?? '—' }} ｜批复人 {{ version.批复人 ?? '—' }}
        </p>

        <div class="coverage-box">
          <div>
            <span class="stat-label">本年度覆盖率</span>
            <strong :class="rateClass(version.coverage_year.rate)">
              {{ version.coverage_year.rate }}%
              （{{ version.coverage_year.covered_count }}/{{ version.coverage_year.total_types }}）
            </strong>
            <span v-if="version.coverage_year.uncovered_types.length" class="miss">
              缺：{{ version.coverage_year.uncovered_types.join('、') }}
            </span>
          </div>
          <div>
            <span class="stat-label">累计覆盖率</span>
            <strong :class="rateClass(version.coverage_all.rate)">
              {{ version.coverage_all.rate }}%
              （{{ version.coverage_all.covered_count }}/{{ version.coverage_all.total_types }}）
            </strong>
          </div>
        </div>

        <h4 class="sub-title">声明事故类别</h4>
        <p>{{ (version.accident_types as string[]).join('、') || '—' }}</p>

        <h4 class="sub-title">预案内容 / 修订说明</h4>
        <p class="content-box">{{ version.预案内容 || '—' }}</p>

        <h4 class="sub-title">挂在该版本下的演练（历史演练沿用本版口径）</h4>
        <table class="data-table">
          <thead>
            <tr><th>演练编号</th><th>演练名称</th><th>事故类别</th><th>演练日期</th><th>结论</th></tr>
          </thead>
          <tbody>
            <tr v-for="drill in version.drills" :key="drill.id">
              <td>{{ drill.演练编号 }}</td>
              <td>{{ drill.演练名称 }}</td>
              <td>{{ drill.事故类别 }}</td>
              <td>{{ drill.演练日期 }}</td>
              <td>{{ drill.演练结论评级 }}</td>
            </tr>
            <tr v-if="!(version.drills as unknown[]).length">
              <td colspan="5" class="empty-state">该版本下暂无演练</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ version: Record<string, any> }>()
defineEmits<{ close: [] }>()

function rateClass(rate: number) {
  if (rate >= 100) return 'cov-full'
  if (rate >= 60) return 'cov-mid'
  return 'cov-low'
}
</script>

<style scoped>
.coverage-box {
  display: flex;
  gap: 32px;
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.coverage-box strong {
  display: block;
  font-size: 18px;
}
.coverage-box .miss {
  color: #b42318;
  font-size: 12px;
  margin-left: 8px;
}
.sub-title {
  font-size: 13px;
  margin: 14px 0 4px;
}
.content-box {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  white-space: pre-wrap;
  font-size: 13px;
  min-height: 48px;
}
.cov-full { color: #067647; }
.cov-mid { color: #b54708; }
.cov-low { color: #b42318; }
</style>
