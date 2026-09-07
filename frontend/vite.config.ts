import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev proxy: /api → FastAPI backend. In production (docker / sandbox preview) the
// built dist/ is served by FastAPI itself on the same origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:3000', changeOrigin: true },
    },
  },
})
