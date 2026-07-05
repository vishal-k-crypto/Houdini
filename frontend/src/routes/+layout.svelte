<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { settings } from '$lib/store';

  const nav = [
    { href: '/', label: 'Run' },
    { href: '/sessions', label: 'Sessions' },
    { href: '/skills', label: 'Skills' },
    { href: '/benchmarks', label: 'Benchmarks' },
    { href: '/settings', label: 'Settings' },
  ];

  // We consider it unconfigured if there is no provider or model set, and we are not on the setup page.
  $: isUnconfigured = (!$settings.provider || !$settings.model) && $page.url.pathname !== '/setup';
</script>

<div class="min-h-screen bg-bg text-text">
  {#if isUnconfigured}
    <div class="bg-gradient-to-r from-blue-900 to-indigo-900 border-b border-blue-800 text-white text-xs px-4 py-2 flex items-center justify-between shadow-md">
      <div class="flex items-center gap-2">
        <span class="text-sm">⚡</span>
        <span>Houdini is not fully configured yet. Select a local LLM, a local CLI agent, or configure your cloud API keys.</span>
      </div>
      <a
        href="/setup"
        class="bg-blue-600 hover:bg-blue-500 text-white font-bold px-3 py-1 rounded transition-colors shadow-sm"
      >
        Run Setup Wizard
      </a>
    </div>
  {/if}

  <nav class="border-b border-border bg-[#0d1117]">
    <div class="max-w-7xl mx-auto px-4">
      <div class="flex items-center gap-6 h-12">
        <span class="font-bold text-blue-400">Houdini</span>
        {#each nav as item}
          <a
            href={item.href}
            class="text-sm transition-colors {$page.url.pathname === item.href ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'}"
          >
            {item.label}
          </a>
        {/each}
      </div>
    </div>
  </nav>

  <slot />
</div>

