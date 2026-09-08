import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { pdfAssets } from './pdf-assets.js'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/',
  publicDir: process.env.VITE_PUBLIC_REFERENCE === 'true' ? fileURLToPath(new URL('../../.cache/pages-public', import.meta.url)) : false,
  resolve: {
    alias: { '@flightmap-app': fileURLToPath(new URL(process.env.VITE_PUBLIC_REFERENCE === 'true' ? './src/PublicApp.tsx' : './src/App.tsx', import.meta.url)) },
  },
  plugins: [react(), ...(process.env.VITE_PUBLIC_REFERENCE === 'true' ? [] : [pdfAssets()])],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
