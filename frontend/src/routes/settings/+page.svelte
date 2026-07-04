<script lang="ts">
  import { onMount } from 'svelte';
  import { settings, fetchProviders, saveSettings } from '$lib/store';
  import type { ProviderInfo } from '$lib/store';

  let providers: ProviderInfo[] = [];
  let saved = false;
  let loading = true;
  let error = '';

  onMount(async () => {
    try {
      providers = await fetchProviders();
    } catch (e: any) {
      error = e.message || String(e);
    } finally {
      loading = false;
    }
  });

  async function handleSave() {
    saved = false;
    error = '';
    try {
      await saveSettings($settings);
      saved = true;
    } catch (e: any) {
      error = e.message || String(e);
    }
  }
</script>

<svelte:head>
  <title>Houdini — Settings</title>
</svelte:head>

<div class="min-h-screen p-4 max-w-4xl mx-auto">
  <h1 class="text-xl font-bold text-blue-400 mb-4">Settings</h1>

  <div class="bg-card border border-border rounded-lg p-6 space-y-4">
    {#if loading}
      <p class="text-sm text-gray-400">Loading providers…</p>
    {:else}
      <div>
        <label class="block text-xs uppercase text-gray-400 mb-1">Provider</label>
        <select bind:value={$settings.provider} class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm">
          {#each providers as p}
            <option value={p.id}>{p.name}{p.available ? ' ✓' : ''}</option>
          {/each}
        </select>
      </div>

      <div>
        <label class="block text-xs uppercase text-gray-400 mb-1">Model</label>
        <input
          bind:value={$settings.model}
          placeholder="qwen3-coder:480b-cloud"
          class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm"
        />
      </div>

      <div>
        <label class="block text-xs uppercase text-gray-400 mb-1">API Key (BYOK)</label>
        <input
          bind:value={$settings.api_key}
          type="password"
          placeholder="sk-..."
          class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm"
        />
        <p class="text-[10px] text-gray-500 mt-1">Stored locally in your browser.</p>
      </div>

      <div>
        <label class="block text-xs uppercase text-gray-400 mb-1">API Base URL</label>
        <input
          bind:value={$settings.api_base}
          placeholder="http://localhost:11434"
          class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm"
        />
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs uppercase text-gray-400 mb-1">Architecture</label>
          <select bind:value={$settings.architecture} class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm">
            <option value="adaptive">Adaptive</option>
            <option value="langgraph">LangGraph</option>
            <option value="legacy">Legacy</option>
          </select>
        </div>
        <div>
          <label class="block text-xs uppercase text-gray-400 mb-1">Checkpoint Path</label>
          <input
            bind:value={$settings.checkpoint_path}
            placeholder="data/checkpoints.db"
            class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm"
          />
        </div>
      </div>

      <div class="flex items-center gap-6 text-sm">
        <label class="flex items-center gap-2">
          <input type="checkbox" bind:checked={$settings.use_enhanced} />
          Enhanced executor
        </label>
        <label class="flex items-center gap-2">
          <input type="checkbox" bind:checked={$settings.thinking_window} />
          Thinking window (native UI)
        </label>
      </div>
    {/if}

    {#if error}
      <p class="text-red-400 text-xs">{error}</p>
    {/if}

    <div class="flex items-center gap-3">
      <button on:click={handleSave} class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold">
        Save Settings
      </button>
      {#if saved}
        <span class="text-green-400 text-sm">Saved</span>
      {/if}
    </div>
  </div>
</div>
