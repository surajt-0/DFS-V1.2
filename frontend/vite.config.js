import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api and /accounts to Django (running on :8000) so the
// browser only ever talks to one origin -- the session/CSRF cookie set by
// Django is then usable by the React app with no CORS gymnastics needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/accounts': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // Evidence exports (CSV/XLSX/JSON) and case PDF reports are plain
      // file-download GETs, so they stay on the legacy same-origin Django
      // endpoints (session cookie is enough) instead of being reimplemented
      // as JSON API calls -- proxy them through in dev the same way.
      '/evidence': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/recovery': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
