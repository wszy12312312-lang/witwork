<script setup lang="ts">
// rareui「Animated counter」交互：数字像里程表一样逐位滚动到新值。
// 每位一格，格内 0-9 纵向排列，靠 translateY 滚动；上下边缘用遮罩淡出而非硬裁。
// 需 --ui-scale 无关；宽度用 1ch + tabular-nums 保证位宽稳定，不抖动。
import { computed, onMounted, ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    value: number;
    /** 每位滚动时长（秒） */
    duration?: number;
    /** 小数位 */
    decimals?: number;
    /** 千分位字符，空串则不分组 */
    separator?: string;
    /** 整数部分最少位数（不足补前导零），用于时钟等定宽场景 */
    padStart?: number;
  }>(),
  { duration: 0.6, decimals: 0, separator: ',', padStart: 0 }
);

function fmt(v: number): string {
  const fixed = Math.abs(v).toFixed(Math.max(0, props.decimals));
  const [ip, dp] = fixed.split('.');
  const padded = props.padStart > 0 ? ip.padStart(props.padStart, '0') : ip;
  const grouped = props.separator ? padded.replace(/\B(?=(\d{3})+(?!\d))/g, props.separator) : padded;
  const sign = v < 0 ? '-' : '';
  return sign + grouped + (dp ? '.' + dp : '');
}

// 挂载时从 0 滚到目标值（进入动画），其后每次变化滚动到新值
const shown = ref(props.value);
onMounted(() => {
  if (props.value === 0) return;
  shown.value = 0;
  requestAnimationFrame(() => (shown.value = props.value));
});
watch(
  () => props.value,
  (v) => {
    shown.value = v;
  }
);

// 以「距末尾的偏移」作 key：位数增减时既有数位保持同一元素，只有新位滑入/末尾淡出
const chars = computed(() => {
  const arr = fmt(shown.value).split('');
  const last = arr.length - 1;
  return arr.map((c, i) => ({ c, digit: /\d/.test(c) ? Number(c) : -1, k: i - last }));
});
</script>

<template>
  <span class="rare-counter">
    <template v-for="ch in chars" :key="ch.k">
      <span v-if="ch.digit >= 0" class="rc-wheel">
        <span class="rc-strip" :style="{ transform: `translateY(${-ch.digit}em)`, transitionDuration: duration + 's' }">
          <span v-for="d in 10" :key="d" class="rc-face">{{ d - 1 }}</span>
        </span>
      </span>
      <span v-else class="rc-mark">{{ ch.c }}</span>
    </template>
  </span>
</template>

<style scoped>
.rare-counter {
  display: inline-flex;
  align-items: baseline;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}
.rc-wheel {
  display: inline-block;
  width: 1ch;
  height: 1em;
  line-height: 1em;
  overflow: hidden;
  vertical-align: baseline;
  /* 上下边缘淡出，模拟里程表窗口，而非硬裁切 */
  -webkit-mask-image: linear-gradient(transparent, #000 24%, #000 76%, transparent);
  mask-image: linear-gradient(transparent, #000 24%, #000 76%, transparent);
}
.rc-strip {
  display: flex;
  flex-direction: column;
  transition-property: transform;
  transition-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
}
.rc-face {
  height: 1em;
  line-height: 1em;
  text-align: center;
}
.rc-mark {
  display: inline-block;
  text-align: center;
}
@media (prefers-reduced-motion: reduce) {
  .rc-strip {
    transition-duration: 0.01ms !important;
  }
}
</style>
