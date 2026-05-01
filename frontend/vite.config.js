import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    base: './', // CRITICAL: Use relative paths for Electron file:// protocol
    server: {
        port: 5173,
        strictPort: true,
    },
    build: {
        outDir: 'dist',
        emptyOutDir: true,
        sourcemap: false, // Disable source maps for production
        rollupOptions: {
            output: {
                manualChunks: {
                    // Split vendor chunks for better caching and smaller initial load
                    'livekit': ['livekit-client', '@livekit/components-react', '@livekit/components-styles'],
                    'react-vendor': ['react', 'react-dom'],
                },
            },
        },
        chunkSizeWarningLimit: 1000, // Warn if chunks exceed 1MB
        assetsDir: 'assets', // Ensure assets use relative paths
    },
    resolve: {
        alias: {
            '@': '/src', // Optional: allows @/components/... imports
        },
    },
})
