import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { fileURLToPath, URL } from 'node:url'

/**
 * @mdi/font declares its @font-face with four formats — eot, woff2, woff and
 * ttf — and Vite emits every file the CSS references. Those four weigh 3.5 MB
 * of the 4.9 MB bundle, and only woff2 is used: a browser picks the first
 * format it supports from the src list, and every browser since ~2015 supports
 * woff2.
 *
 * This rewrites the src descriptor to keep woff2 alone, so the other three are
 * no longer referenced and never emitted. Dropping them costs icon rendering on
 * browsers older than woff2 support, which the Observatory — served on
 * localhost for an internal tool — does not target.
 */
function mdiWoff2Only(): Plugin {
  return {
    name: 'mdi-woff2-only',
    enforce: 'pre',
    transform(code, id) {
      if (!id.includes('materialdesignicons.css')) return null
      const woff2 = code.match(/url\(("[^"]*\.woff2[^"]*")\)\s*format\("woff2"\)/)
      if (!woff2) {
        // The upstream CSS changed shape; fail loudly rather than silently
        // shipping 3.5 MB of legacy fonts again.
        this.error('mdi-woff2-only: no woff2 source found in materialdesignicons.css')
      }
      return code.replace(
        /src:[^;]*;\s*src:[^;]*;/,
        `src: url(${woff2[1]}) format("woff2");`,
      )
    },
  }
}

export default defineConfig({
  plugins: [
    mdiWoff2Only(),
    vue(),
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/ws': {
        target: 'ws://127.0.0.1:8765',
        ws: true,
      },
    },
  },
})
