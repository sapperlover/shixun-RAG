<script setup lang="ts">
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { LABEL_ZH, RELATION_ZH, type Path } from '@/types/qa'

echarts.use([GraphChart, TooltipComponent, CanvasRenderer])

const props = defineProps<{ paths: Path[] }>()
const el = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined

const COLORS: Record<string, string> = {
  College: '#64748b',
  Professional: '#2563eb',
  ProgramPlan: '#7c3aed',
  CourseCategory: '#0891b2',
  Course: '#16a34a',
  RuleClause: '#d97706',
}

function render() {
  if (!chart) return
  // 每条路径一行，节点按跳次从左到右排列；同一节点在多条路径中只画一次
  const pos = new Map<string, [number, number]>()
  const nodes: object[] = []
  props.paths.forEach((p, row) => {
    // 按边的连接顺序排列节点（边的 from/to 是存储方向，展示时按路径顺序）
    p.nodes.forEach((n, col) => {
      if (pos.has(n.node_id)) return
      pos.set(n.node_id, [col * 220, row * 120])
      nodes.push({
        id: n.node_id,
        name: n.name,
        x: col * 220,
        y: row * 120,
        symbolSize: 18,
        itemStyle: { color: COLORS[n.label] },
        label: { show: true, position: 'bottom', formatter: `${LABEL_ZH[n.label]}\n${n.name}` },
      })
    })
  })
  const links = props.paths.flatMap((p) =>
    p.edges.map((e) => ({
      source: e.from,
      target: e.to,
      label: { show: true, formatter: RELATION_ZH[e.type] },
    })),
  )
  chart.setOption({
    tooltip: {},
    series: [
      {
        type: 'graph',
        layout: 'none',
        roam: true,
        data: nodes,
        links,
        edgeSymbol: ['none', 'arrow'],
        edgeLabel: { fontSize: 12 },
        lineStyle: { width: 2, color: '#94a3b8' },
      },
    ],
  })
}

onMounted(() => {
  chart = echarts.init(el.value!)
  render()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
watch(() => props.paths, render, { deep: true })

function onResize() {
  chart?.resize()
}
</script>

<template>
  <div ref="el" class="graph" />
</template>

<style scoped>
.graph {
  width: 100%;
  height: 280px;
}
</style>
