<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchProviders } from '$lib/store';
  import type { ProviderInfo } from '$lib/store';

  interface Skill {
    id: string;
    name: string;
    description: string;
    triggers: string[];
    tags: string[];
    priority: number;
    matched: boolean;
  }

  let skills: Skill[] = [];
  let task = '';
  let loading = true;
  let error = '';

  async function loadSkills() {
    loading = true;
    error = '';
    try {
      const url = task.trim()
        ? `/api/skills?task=${encodeURIComponent(task)}`
        : '/api/skills';
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed to fetch skills: ${res.status}`);
      const data = await res.json();
      skills = data.skills || [];
    } catch (e: any) {
      error = e.message || String(e);
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    loadSkills();
  });
</script>

<svelte:head>
  <title>Houdini — Skills</title>
</svelte:head>

<div class="min-h-screen p-4 max-w-4xl mx-auto">
  <h1 class="text-xl font-bold text-blue-400 mb-4">Skills</h1>

  <div class="bg-card border border-border rounded-lg p-4 mb-4">
    <p class="text-sm text-gray-300 mb-2">
      Skills are reusable instruction files the agent consults for common task families.
      Type a task to see which skills would be injected into the planner prompt.
    </p>
    <div class="flex gap-2">
      <input
        bind:value={task}
        placeholder="Describe a task..."
        class="flex-1 bg-[#0d1117] border border-border rounded p-2 text-sm"
        on:keydown={(e) => e.key === 'Enter' && loadSkills()}
      />
      <button
        on:click={loadSkills}
        class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold"
      >
        Match
      </button>
    </div>
  </div>

  {#if loading}
    <p class="text-sm text-gray-400">Loading skills…</p>
  {:else if error}
    <p class="text-red-400 text-sm">{error}</p>
  {:else}
    <div class="space-y-3">
      {#each skills as skill (skill.id)}
        <div class="bg-card border {skill.matched ? 'border-blue-500/50' : 'border-border'} rounded-lg p-4">
          <div class="flex justify-between items-start">
            <div>
              <h2 class="text-sm font-semibold text-gray-200">{skill.name}</h2>
              <p class="text-xs text-gray-400 mt-1">{skill.description}</p>
            </div>
            {#if skill.matched}
              <span class="text-[10px] px-2 py-0.5 rounded bg-blue-900/40 text-blue-400">matched</span>
            {/if}
          </div>
          <div class="flex flex-wrap gap-2 mt-3">
            {#each skill.triggers as trigger}
              <span class="text-[10px] px-2 py-0.5 rounded bg-[#0d1117] text-gray-400 border border-border">{trigger}</span>
            {/each}
          </div>
          <div class="flex flex-wrap gap-2 mt-2">
            {#each skill.tags as tag}
              <span class="text-[10px] px-2 py-0.5 rounded bg-[#0d1117] text-gray-500">#{tag}</span>
            {/each}
          </div>
        </div>
      {:else}
        <p class="text-sm text-gray-500 italic">No skills loaded.</p>
      {/each}
    </div>
  {/if}
</div>
