import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    resolve: {
      // La dep @poulidor/hub-socle est un lien file: (symlink node_modules ->
      // HUBsocle) : préserver le chemin à travers le symlink pour que les
      // peer deps du socle (react, lucide-react, @tanstack/react-query) se
      // résolvent depuis les node_modules de l'app hôte.
      preserveSymlinks: true,
    },
    optimizeDeps: {
      esbuildOptions: {
        loader: { '.jsx': 'jsx' },
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      proxy: {
        '/api': {
          target: 'http://api:8000',
          changeOrigin: true,
        },
        '/hub': {
          target: `http://${env.HUB_HOST || 'localhost'}:${env.HUB_API_PORT || '8000'}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/hub/, ''),
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
