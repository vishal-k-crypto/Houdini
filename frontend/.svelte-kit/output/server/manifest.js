export const manifest = (() => {
function __memo(fn) {
	let value;
	return () => value ??= (value = fn());
}

return {
	appDir: "_app",
	appPath: "_app",
	assets: new Set([]),
	mimeTypes: {},
	_: {
		client: {start:"_app/immutable/entry/start.BQju_akj.js",app:"_app/immutable/entry/app.DPzc7ndm.js",imports:["_app/immutable/entry/start.BQju_akj.js","_app/immutable/chunks/BhkRMEIu.js","_app/immutable/chunks/DdeEKLTK.js","_app/immutable/chunks/DUGLEWLU.js","_app/immutable/chunks/B6sNV5qq.js","_app/immutable/chunks/Dt5TU4Rc.js","_app/immutable/chunks/DEQAWB8m.js","_app/immutable/chunks/BygRehY-.js","_app/immutable/chunks/DhDlnH10.js","_app/immutable/entry/app.DPzc7ndm.js","_app/immutable/chunks/DdeEKLTK.js","_app/immutable/chunks/DUGLEWLU.js","_app/immutable/chunks/B6sNV5qq.js","_app/immutable/chunks/Dt5TU4Rc.js","_app/immutable/chunks/DEQAWB8m.js","_app/immutable/chunks/BygRehY-.js"],stylesheets:[],fonts:[],uses_env_dynamic_public:false},
		nodes: [
			__memo(() => import('./nodes/0.js')),
			__memo(() => import('./nodes/1.js')),
			__memo(() => import('./nodes/2.js')),
			__memo(() => import('./nodes/3.js')),
			__memo(() => import('./nodes/4.js'))
		],
		remotes: {
			
		},
		routes: [
			{
				id: "/",
				pattern: /^\/$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 2 },
				endpoint: null
			},
			{
				id: "/sessions",
				pattern: /^\/sessions\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 3 },
				endpoint: null
			},
			{
				id: "/settings",
				pattern: /^\/settings\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 4 },
				endpoint: null
			}
		],
		prerendered_routes: new Set([]),
		matchers: async () => {
			
			return {  };
		},
		server_assets: {}
	}
}
})();
