import { defineConfig, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';
const backend = 'http://127.0.0.1:9090';
const secureProxy: ProxyOptions = {
  target: backend,
  changeOrigin: true,
  headers: { Origin: backend },
};

export default defineConfig({
  root: import.meta.dirname,
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/analyze': secureProxy,
      '/calibrate': secureProxy,
      '/jobs': secureProxy,
      '/history': secureProxy,
      '/metrics': secureProxy,
      '/agents': secureProxy,
      '/analysis': secureProxy,
      '/uploads': secureProxy,
    },
  },
});
