import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Backend target works in two modes:
//   • bare metal      → http://127.0.0.1:8765 (default)
//   • docker compose  → BACKEND_HTTP_TARGET=http://backend:8765
const HTTP_TARGET = process.env.BACKEND_HTTP_TARGET || 'http://127.0.0.1:8765';
const WS_TARGET = process.env.BACKEND_WS_TARGET || 'ws://127.0.0.1:8765';
const HMR_CLIENT_PORT = Number(process.env.VITE_HMR_CLIENT_PORT) || undefined;

// LAN_MODE (see backend/app/security.py + Makefile `dev-lan`): off by
// default, this server binds loopback only, so nothing on the LAN can send
// it a request at all (the Host-header trust gap the backend closes via
// Settings.lan_mode simply doesn't arise). Set LAN_MODE=1/true to bind
// every interface for `make dev-lan`.
const LAN_MODE = /^(1|true)$/i.test(process.env.LAN_MODE || '');

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: LAN_MODE ? true : '127.0.0.1',
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
