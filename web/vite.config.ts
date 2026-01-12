import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to FastAPI during development
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        // Enable cookie forwarding
        cookieDomainRewrite: 'localhost',
        secure: false,
      },
    },
  },
})
