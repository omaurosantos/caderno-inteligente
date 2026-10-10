import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

export default mergeConfig(viteConfig, defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // Only styles.css is processed, so the contrast test can read the real design tokens.
    css: { include: [/styles\.css(\?raw)?$/] },
    restoreMocks: true,
    // Recharts tem centenas de módulos: pré-empacotado, o primeiro teste de cada arquivo não estoura a espera.
    deps: { optimizer: { web: { enabled: true, include: ['recharts'] } } },
    testTimeout: 15000,
  },
}));
