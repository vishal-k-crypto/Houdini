<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';

  const nav = [
    { href: '/', label: 'Run' },
    { href: '/sessions', label: 'Sessions' },
    { href: '/skills', label: 'Skills' },
    { href: '/benchmarks', label: 'Benchmarks' },
    { href: '/settings', label: 'Settings' },
  ];
</script>

<div class="min-h-screen bg-bg text-text">
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
