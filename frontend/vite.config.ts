import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the backend so the browser sees a single origin and
// development never needs CORS. In production the dashboard is served statically and
// VITE_API_BASE points the client straight at the API instead.
//
// `loadEnv` is used rather than `process.env` so this file typechecks without pulling in
// @types/node — the dashboard's only build dependency is Vite itself.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const target = env.VITE_API_TARGET || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  }
})
