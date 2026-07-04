
// this file is generated — do not edit it


/// <reference types="@sveltejs/kit" />

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module only includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/private';
 * 
 * console.log(ENVIRONMENT); // => "production"
 * console.log(PUBLIC_BASE_URL); // => throws error during build
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/private' {
	export const SVELTEKIT_FORK: string;
	export const _: string;
	export const npm_node_execpath: string;
	export const HERMES_REAL_HOME: string;
	export const NODE_ENV: string;
	export const TERMINAL_CONTAINER_DISK: string;
	export const TERMINAL_DOCKER_FORWARD_ENV: string;
	export const TERMINAL_DOCKER_RUN_AS_HOST_USER: string;
	export const npm_config_user_agent: string;
	export const npm_lifecycle_script: string;
	export const PYTHONPATH: string;
	export const npm_config_cache: string;
	export const HOME: string;
	export const NODE: string;
	export const TERMINAL_SINGULARITY_IMAGE: string;
	export const TERMINAL_CWD: string;
	export const HERMES_RPC_SOCKET: string;
	export const npm_package_version: string;
	export const TERMINAL_TIMEOUT: string;
	export const npm_lifecycle_event: string;
	export const PWD: string;
	export const PYTHONUTF8: string;
	export const npm_config_node_gyp: string;
	export const npm_command: string;
	export const __CF_USER_TEXT_ENCODING: string;
	export const npm_config_init_module: string;
	export const PYTHONDONTWRITEBYTECODE: string;
	export const TERMINAL_CONTAINER_MEMORY: string;
	export const npm_config_npm_version: string;
	export const npm_execpath: string;
	export const npm_config_userconfig: string;
	export const TERMINAL_ENV: string;
	export const npm_package_json: string;
	export const TERMINAL_DOCKER_ENV: string;
	export const TERMINAL_DOCKER_EXTRA_ARGS: string;
	export const USER: string;
	export const PYTHONIOENCODING: string;
	export const TERMINAL_CONTAINER_PERSISTENT: string;
	export const LOGNAME: string;
	export const npm_config_local_prefix: string;
	export const npm_package_name: string;
	export const npm_config_noproxy: string;
	export const SHELL: string;
	export const COLOR: string;
	export const TERMINAL_HOME_MODE: string;
	export const TERMINAL_DOCKER_VOLUMES: string;
	export const npm_config_prefix: string;
	export const SHLVL: string;
	export const TERMINAL_LIFETIME_SECONDS: string;
	export const TMPDIR: string;
	export const LC_CTYPE: string;
	export const PATH: string;
	export const TERMINAL_DOCKER_IMAGE: string;
	export const TERMINAL_MODAL_IMAGE: string;
	export const TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE: string;
	export const npm_config_globalconfig: string;
	export const TERMINAL_DAYTONA_IMAGE: string;
	export const INIT_CWD: string;
	export const EDITOR: string;
	export const TERMINAL_CONTAINER_CPU: string;
	export const HERMES_HOME: string;
	export const npm_config_global_prefix: string;
	export const TERMINAL_PERSISTENT_SHELL: string;
}

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/public';
 * 
 * console.log(ENVIRONMENT); // => throws error during build
 * console.log(PUBLIC_BASE_URL); // => "http://site.com"
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/public' {
	
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/private';
 * 
 * console.log(env.ENVIRONMENT); // => "production"
 * console.log(env.PUBLIC_BASE_URL); // => undefined
 * ```
 */
declare module '$env/dynamic/private' {
	export const env: {
		SVELTEKIT_FORK: string;
		_: string;
		npm_node_execpath: string;
		HERMES_REAL_HOME: string;
		NODE_ENV: string;
		TERMINAL_CONTAINER_DISK: string;
		TERMINAL_DOCKER_FORWARD_ENV: string;
		TERMINAL_DOCKER_RUN_AS_HOST_USER: string;
		npm_config_user_agent: string;
		npm_lifecycle_script: string;
		PYTHONPATH: string;
		npm_config_cache: string;
		HOME: string;
		NODE: string;
		TERMINAL_SINGULARITY_IMAGE: string;
		TERMINAL_CWD: string;
		HERMES_RPC_SOCKET: string;
		npm_package_version: string;
		TERMINAL_TIMEOUT: string;
		npm_lifecycle_event: string;
		PWD: string;
		PYTHONUTF8: string;
		npm_config_node_gyp: string;
		npm_command: string;
		__CF_USER_TEXT_ENCODING: string;
		npm_config_init_module: string;
		PYTHONDONTWRITEBYTECODE: string;
		TERMINAL_CONTAINER_MEMORY: string;
		npm_config_npm_version: string;
		npm_execpath: string;
		npm_config_userconfig: string;
		TERMINAL_ENV: string;
		npm_package_json: string;
		TERMINAL_DOCKER_ENV: string;
		TERMINAL_DOCKER_EXTRA_ARGS: string;
		USER: string;
		PYTHONIOENCODING: string;
		TERMINAL_CONTAINER_PERSISTENT: string;
		LOGNAME: string;
		npm_config_local_prefix: string;
		npm_package_name: string;
		npm_config_noproxy: string;
		SHELL: string;
		COLOR: string;
		TERMINAL_HOME_MODE: string;
		TERMINAL_DOCKER_VOLUMES: string;
		npm_config_prefix: string;
		SHLVL: string;
		TERMINAL_LIFETIME_SECONDS: string;
		TMPDIR: string;
		LC_CTYPE: string;
		PATH: string;
		TERMINAL_DOCKER_IMAGE: string;
		TERMINAL_MODAL_IMAGE: string;
		TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE: string;
		npm_config_globalconfig: string;
		TERMINAL_DAYTONA_IMAGE: string;
		INIT_CWD: string;
		EDITOR: string;
		TERMINAL_CONTAINER_CPU: string;
		HERMES_HOME: string;
		npm_config_global_prefix: string;
		TERMINAL_PERSISTENT_SHELL: string;
		[key: `PUBLIC_${string}`]: undefined;
		[key: `${string}`]: string | undefined;
	}
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://example.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/public';
 * console.log(env.ENVIRONMENT); // => undefined, not public
 * console.log(env.PUBLIC_BASE_URL); // => "http://example.com"
 * ```
 * 
 * ```
 * 
 * ```
 */
declare module '$env/dynamic/public' {
	export const env: {
		[key: `PUBLIC_${string}`]: string | undefined;
	}
}
