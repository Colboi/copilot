<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'

const appWindow = getCurrentWindow()
const maximized = ref(false)
const focused = ref(true)
let disposed = false
const listeners = []

async function trackWindowEvents() {
  maximized.value = await appWindow.isMaximized()
  const resizeListener = await appWindow.onResized(async () => {
    maximized.value = await appWindow.isMaximized()
  })
  const focusListener = await appWindow.onFocusChanged(({ payload }) => {
    focused.value = payload
  })
  if (disposed) {
    resizeListener()
    focusListener()
    return
  }
  listeners.push(resizeListener, focusListener)
}

onMounted(trackWindowEvents)
onBeforeUnmount(() => {
  disposed = true
  listeners.forEach((unlisten) => unlisten())
})
</script>

<template>
  <header class="window-titlebar" :class="{ 'is-unfocused': !focused }">
    <div class="window-drag-region" data-tauri-drag-region title="拖动窗口，双击最大化或还原">
      <span class="window-brand-mark" aria-hidden="true">C</span>
      <span class="window-title">Colpilot</span>
      <span class="window-subtitle">你的日常工具</span>
    </div>
    <div class="window-controls" aria-label="窗口控制">
      <button type="button" aria-label="最小化" title="最小化" @click="appWindow.minimize()">
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10" /></svg>
      </button>
      <button type="button" :aria-label="maximized ? '还原窗口' : '最大化'" :title="maximized ? '还原窗口' : '最大化'" @click="appWindow.toggleMaximize()">
        <svg v-if="maximized" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 5V3h7v7h-2" /><rect x="3" y="6" width="7" height="7" rx="1" /></svg>
        <svg v-else viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="3" width="10" height="10" rx="1" /></svg>
      </button>
      <button type="button" class="window-close" aria-label="关闭到托盘" title="关闭到托盘" @click="appWindow.close()">
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
      </button>
    </div>
  </header>
</template>
