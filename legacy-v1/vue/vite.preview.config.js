// Demo/preview-only build config — NOT part of the real deployment path
// (see docker/web.Dockerfile for that). Produces a single self-contained
// HTML file (JS + CSS inlined) so the UI can be opened or published
// without running api/, ocr/, or a static file server at all. Every
// backend-dependent feature (saving a notice, the chat's document
// upload, live API health, the saved-notices list) fails gracefully in
// this mode exactly as it does when the real api/ is simply offline —
// this build doesn't fake or mock any of that data.
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

export default defineConfig({
  plugins: [vue(), tailwindcss(), viteSingleFile()],
  build: {
    outDir: 'dist-preview',
    assetsInlineLimit: 100000000,
    cssCodeSplit: false
  }
});
