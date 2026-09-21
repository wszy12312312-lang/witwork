/* rareui 风格微交互（Vue 指令）
 * 参考 https://www.rareui.com/components 的邻近吸附 / 磁吸交互：
 * 指针靠近操作按钮时，按钮向指针方向轻微位移并放大，离开时以临界阻尼弹簧归位。
 * 纯 CSS transform 实现，不触发重排，尊重 prefers-reduced-motion。
 */
import type { Directive } from 'vue';

export interface MagnetOpts {
  /** 最大位移像素 */
  strength?: number;
  /** 最大放大倍数 */
  scale?: number;
  /** 容器内参与吸附的子元素选择器 */
  selector?: string;
  /** 影响半径 = 元素尺寸 × radius */
  radius?: number;
}

function reducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** 单元素磁吸：<button v-magnetic>…</button> */
export const vMagnetic: Directive<HTMLElement, MagnetOpts | undefined> = {
  mounted(el, binding) {
    if (typeof window === 'undefined' || reducedMotion()) return;
    const strength = binding.value?.strength ?? 6;
    const maxScale = binding.value?.scale ?? 1.07;

    const move = (e: MouseEvent) => {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const radius = Math.max(r.width, r.height) * 1.8;
      const f = Math.max(0, 1 - Math.hypot(dx, dy) / radius);
      if (f <= 0) {
        el.style.transform = '';
        return;
      }
      const tx = (dx / radius) * strength * f;
      const ty = (dy / radius) * strength * f;
      el.style.transition = 'transform 0.06s linear';
      el.style.transform = `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${(1 + (maxScale - 1) * f).toFixed(3)})`;
    };
    const leave = () => {
      el.style.transition = 'transform 0.45s cubic-bezier(0.22, 1, 0.36, 1)';
      el.style.transform = '';
    };
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseleave', leave);
    (el as HTMLElement & { __rareOff?: () => void }).__rareOff = () => {
      el.removeEventListener('mousemove', move);
      el.removeEventListener('mouseleave', leave);
    };
  },
  unmounted(el) {
    (el as HTMLElement & { __rareOff?: () => void }).__rareOff?.();
  },
};

/** 容器级磁吸栏：整排按钮随指针邻近度响应，一个指令管住全部操作按钮。
 *  用法：<div class="bar" v-magnet-rail="{ selector: 'button' }">…</div> */
export const vMagnetRail: Directive<HTMLElement, MagnetOpts | undefined> = {
  mounted(el, binding) {
    if (typeof window === 'undefined' || reducedMotion()) return;
    const strength = binding.value?.strength ?? 7;
    const maxScale = binding.value?.scale ?? 1.09;
    const selector = binding.value?.selector ?? 'button';
    const radiusMul = binding.value?.radius ?? 2.2;

    const kids = () => Array.from(el.querySelectorAll<HTMLElement>(selector));

    const move = (e: MouseEvent) => {
      for (const k of kids()) {
        const r = k.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        const dx = e.clientX - cx;
        const dy = e.clientY - cy;
        const radius = Math.max(r.width, r.height) * radiusMul;
        const f = Math.max(0, 1 - Math.hypot(dx, dy) / radius);
        if (f <= 0) {
          k.style.transform = '';
          continue;
        }
        const tx = (dx / radius) * strength * f;
        const ty = (dy / radius) * strength * f;
        k.style.transition = 'transform 0.06s linear';
        k.style.transform = `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${(1 + (maxScale - 1) * f).toFixed(3)})`;
      }
    };
    const leave = () => {
      for (const k of kids()) {
        k.style.transition = 'transform 0.45s cubic-bezier(0.22, 1, 0.36, 1)';
        k.style.transform = '';
      }
    };
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseleave', leave);
    (el as HTMLElement & { __rareOff?: () => void }).__rareOff = () => {
      el.removeEventListener('mousemove', move);
      el.removeEventListener('mouseleave', leave);
    };
  },
  unmounted(el) {
    (el as HTMLElement & { __rareOff?: () => void }).__rareOff?.();
  },
};
