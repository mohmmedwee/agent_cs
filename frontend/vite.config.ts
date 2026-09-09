import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build straight into web/dist, which is what FastAPI serves. The output is
// self-contained — no CDN at runtime — so the app still works offline once
// built, even though building needs npm.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../web/dist',
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` talks to the Python server for everything under /api.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
