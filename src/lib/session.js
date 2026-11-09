import { computed, shallowRef, triggerRef } from 'vue'
import { parseSave, serializeSave } from './codec.js'
import { attach } from './save.js'

// One snapshot per user action. A failed multi-item edit rolls back as a unit.
export function useSaveSession() {
  const state = shallowRef(null)
  const previous = shallowRef([])
  const current = shallowRef('')
  const saved = shallowRef('')
  let originalText = ''

  function remember(text, snapshot = current.value) {
    originalText = text
    saved.value = snapshot
  }

  function load(text) {
    const next = attach(parseSave(text))
    current.value = serializeSave(next.doc)
    state.value = next
    previous.value = []
    remember(text)
  }

  function edit(action) {
    const before = current.value
    try {
      const result = action()
      const after = serializeSave(state.value.doc)
      if (after !== before) {
        // Large fog maps can grow to megabytes. Keep the latest undo even when
        // that single snapshot exceeds the normal history budget.
        const history = [...previous.value.slice(-49), before]
        let chars = history.reduce((n, entry) => n + entry.length, 0)
        while (history.length > 1 && chars > 8 * 1024 * 1024) chars -= history.shift().length
        previous.value = history
        current.value = after
        triggerRef(state)
      }
      return { changed: after !== before, result }
    } catch (err) {
      state.value = attach(parseSave(before))
      throw err
    }
  }

  function undo() {
    if (!previous.value.length) return
    current.value = previous.value.at(-1)
    previous.value = previous.value.slice(0, -1)
    state.value = attach(parseSave(current.value))
  }

  function fileText() {
    if (current.value === saved.value) return originalText
    const bom = originalText.startsWith('\uFEFF') ? '\uFEFF' : ''
    return bom + current.value + (originalText.match(/\r?\n$/)?.[0] || '')
  }

  return {
    state,
    current,
    load,
    edit,
    undo,
    remember,
    fileText,
    dirty: computed(() => current.value !== saved.value),
    canUndo: computed(() => previous.value.length > 0),
  }
}
