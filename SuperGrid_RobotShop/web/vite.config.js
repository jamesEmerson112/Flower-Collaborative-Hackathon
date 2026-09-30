import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  // 5175 so it never collides with the original Robot Workshop dev server (5174).
  // /api goes to the SuperGrid bridge (SuperGrid_RobotShop/bridge.py) during `npm run dev`;
  // in production the bridge serves dist/ itself, so the proxy is dev-only.
  server: {
    host: '127.0.0.1',
    port: 5175,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8765', changeOrigin: false } },
  },
  build: { chunkSizeWarningLimit: 800 },
});
