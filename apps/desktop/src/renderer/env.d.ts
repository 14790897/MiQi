import type { MiQiAPI } from '../preload/index'

declare global {
  interface Window {
    miqi: MiQiAPI
  }
}
