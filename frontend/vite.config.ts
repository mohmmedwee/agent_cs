import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// Build straight into web/dist, which is what FastAPI serves. The output is
// self-contained — no CDN at runtime — so the app still works offline once
// built, even though building needs npm.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: '../web/dist',
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` talks to the Python server for everything under /api.
    // `changeOrigin` keeps the session cookie's host matching in dev.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
