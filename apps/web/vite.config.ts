import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { pdfAssets } from './pdf-assets.js'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), pdfAssets()],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
