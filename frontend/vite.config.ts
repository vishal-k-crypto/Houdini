import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			'/api': {
				target: 'http://127.0.0.1:8420',
				changeOrigin: true,
				ws: false
			},
			'/ws': {
				target: 'ws://127.0.0.1:8420',
				ws: true,
				changeOrigin: true
			}
		}
	}
});
