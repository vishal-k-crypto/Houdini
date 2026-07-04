<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    tasks,
    health,
    wsConnected,
    terminal,
    screenshots,
    events,
    selectedTaskId,
    selectedTask,
    settings,
    submitTask,
    fetchTasks,
    fetchHealth,
    connectWebSocket
  } from '$lib/store';
  import type { WebSocket as WS } from 'vite';

  let taskInput = '';
  let busy = false;
  let error = '';
  let ws: WebSocket | null = null;
  let polling: number;
  let terminalFollow = true;

  onMount(() => {
    fetchTasks();
    fetchHealth();
    ws = connectWebSocket();
    polling = window.setInterval(() => {
      fetchHealth();
      fetchTasks();
    }, 3000);
  });

  onDestroy(() => {
    ws?.close();
    window.clearInterval(polling);
  });

  async function handleSubmit() {
    if (!taskInput.trim()) return;
    busy = true;
    error = '';
    try {
      await submitTask(taskInput, {
        provider: $settings.provider || undefined,
        model: $settings.model || undefined,
        architecture: $settings.architecture,
        use_enhanced: $settings.use_enhanced,
        cloud_endpoint: $settings.api_base || undefined,
        checkpoint_path: $settings.checkpoint_path || undefined
      });
      taskInput = '';
    } catch (e: any) {
      error = e.message || String(e);
    } finally {
      busy = false;
    }
  }

  function statusColor(status: string) {
    if (status === 'completed') return 'bg-green-900/40 text-green-400';
    if (status === 'failed') return 'bg-red-900/40 text-red-400';
    if (status === 'running') return 'bg-blue-900/40 text-blue-400';
    return 'bg-orange-900/40 text-orange-400';
  }

  function truncate(s: string, n: number) {
    return s.length > n ? s.slice(0, n) + '…' : s;
  }
</script>

<svelte:head>
  <title>Houdini — Run</title>
</svelte:head>

<div class="min-h-screen p-4">
  <header class="flex items-center justify-between mb-4">
    <h1 class="text-xl font-bold text-blue-400">Houdini Agent</h1>
    <div class="flex items-center gap-3">
      <span class="text-xs text-gray-400">Status: {$health?.status || '—'}</span>
      <span class="flex items-center gap-1 text-xs">
        <span class="w-2 h-2 rounded-full {$wsConnected ? 'bg-green-400' : 'bg-red-400'}"></span>
        {$wsConnected ? 'live' : 'offline'}
      </span>
    </div>
  </header>

  <div class="grid grid-cols-12 gap-4">
    <!-- Left column: input + task list -->
    <div class="col-span-12 lg:col-span-4 space-y-4">
      <div class="bg-card border border-border rounded-lg p-4">
        <h2 class="text-xs uppercase text-gray-400 mb-2">New Task</h2>
        <textarea
          bind:value={taskInput}
          disabled={busy}
          placeholder="Describe the task..."
          class="w-full h-24 bg-[#0d1117] border border-border rounded p-2 text-sm focus:border-blue-500 outline-none resize-none"
        ></textarea>
        <div class="flex justify-between items-center mt-2">
          <span class="text-xs text-gray-500">Using {$settings.provider || 'ollama'} / {$settings.model || 'default'}</span>
          <button
            on:click={handleSubmit}
            disabled={busy || !taskInput.trim()}
            class="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm font-semibold"
          >
            {busy ? 'Starting…' : 'Run'}
          </button>
        </div>
        {#if error}
          <p class="text-red-400 text-xs mt-2">{error}</p>
        {/if}
      </div>

      <div class="bg-card border border-border rounded-lg p-4">
        <h2 class="text-xs uppercase text-gray-400 mb-2">Sessions</h2>
        <div class="max-h-80 overflow-y-auto space-y-2">
          {#each $tasks as task (task.task_id)}
            <button
              on:click={() => selectedTaskId.set(task.task_id)}
              class="w-full text-left border border-border rounded p-2 hover:bg-[#0d1117] transition-colors"
              class:ring-2={$selectedTaskId === task.task_id}
              class:ring-blue-500={$selectedTaskId === task.task_id}
            >
              <div class="flex justify-between items-center">
                <span class="text-xs font-mono text-gray-400">{task.task_id}</span>
                <span class="text-[10px] px-2 py-0.5 rounded {statusColor(task.status)}">{task.status}</span>
              </div>
              <p class="text-xs text-gray-300 mt-1 truncate">{truncate(task.task, 60)}</p>
              <p class="text-[10px] text-gray-500 mt-1">{task.architecture}</p>
            </button>
          {:else}
            <p class="text-xs text-gray-500 italic">No sessions yet.</p>
          {/each}
        </div>
      </div>
    </div>

    <!-- Center: live view -->
    <div class="col-span-12 lg:col-span-4 space-y-4">
      <div class="bg-card border border-border rounded-lg p-4">
        <h2 class="text-xs uppercase text-gray-400 mb-2">Live View</h2>
        {#if $screenshots.length > 0}
          <img
            src={$screenshots[0].image_base64 || `data:image/png;base64,${$screenshots[0].image}`}
            alt="latest screenshot"
            class="w-full rounded border border-border"
          />
          <p class="text-[10px] text-gray-500 mt-1">{$screenshots[0].timestamp}</p>
        {:else}
          <div class="w-full h-64 bg-[#0d1117] border border-dashed border-border rounded flex items-center justify-center text-xs text-gray-500">
            No live screenshot yet
          </div>
        {/if}
      </div>

      {#if $selectedTask}
        <div class="bg-card border border-border rounded-lg p-4">
          <h2 class="text-xs uppercase text-gray-400 mb-2">Selected Session</h2>
          <p class="text-xs font-mono text-gray-400 mb-1">{$selectedTask.task_id}</p>
          <p class="text-sm text-gray-200">{$selectedTask.task}</p>
          <p class="text-xs text-gray-500 mt-2">Architecture: {$selectedTask.architecture}</p>
          <p class="text-xs text-gray-500">Status: {$selectedTask.status}</p>
          {#if $selectedTask.result}
            <pre class="mt-2 text-[10px] bg-[#0d1117] border border-border rounded p-2 overflow-auto max-h-40">{JSON.stringify($selectedTask.result, null, 2)}</pre>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Right: thinking log + terminal -->
    <div class="col-span-12 lg:col-span-4 space-y-4">
      <div class="bg-card border border-border rounded-lg p-4">
        <h2 class="text-xs uppercase text-gray-400 mb-2">Thinking Log</h2>
        <div class="h-64 overflow-y-auto bg-[#0d1117] border border-border rounded p-2 text-[11px] space-y-1">
          {#each $events as ev (ev.ts + ev.type)}
            <div class="border-b border-[#21262d] pb-1">
              <span class="text-gray-500 mr-1">{ev.ts || '—'}</span>
              <span class="text-blue-300">{ev.type}</span>
              <span class="text-gray-300">{truncate(JSON.stringify(ev), 120)}</span>
            </div>
          {:else}
            <p class="text-gray-500 italic">Waiting for events…</p>
          {/each}
        </div>
      </div>

      <div class="bg-card border border-border rounded-lg p-4">
        <h2 class="text-xs uppercase text-gray-400 mb-2">Terminal</h2>
        <div class="h-64 overflow-y-auto bg-[#0d1117] border border-border rounded p-2 text-[11px] font-mono space-y-0.5">
          {#each $terminal as line (line.ts + line.text)}
            <div>
              <span class="text-gray-500 mr-2">{line.ts}</span>
              <span class="text-gray-300">{line.text}</span>
            </div>
          {:else}
            <p class="text-gray-500 italic">No terminal output.</p>
          {/each}
        </div>
      </div>
    </div>
  </div>
</div>
