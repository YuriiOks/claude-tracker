import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Backend target works in two modes:
//   • bare metal      → http://127.0.0.1:8765 (default)
//   • docker compose  → BACKEND_HTTP_TARGET=http://backend:8765
const HTTP_TARGET = process.env.BACKEND_HTTP_TARGET || 'http://127.0.0.1:8765';
const WS_TARGET = process.env.BACKEND_WS_TARGET || 'ws://127.0.0.1:8765';
const HMR_CLIENT_PORT = Number(process.env.VITE_HMR_CLIENT_PORT) || undefined;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    hmr: HMR_CLIENT_PORT ? { clientPort: HMR_CLIENT_PORT } : true,
    proxy: {
      '/api': {
        target: HTTP_TARGET,
        changeOrigin: false,
      },
      '/ws': {
        target: WS_TARGET,
        ws: true,
        changeOrigin: false,
      },
    },
  },
});
