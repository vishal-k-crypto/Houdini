<script lang="ts">
  import { onMount } from 'svelte';
  import { tasks, fetchTasks, selectedTaskId } from '$lib/store';

  onMount(() => {
    fetchTasks();
  });

  function statusColor(status: string) {
    if (status === 'completed') return 'bg-green-900/40 text-green-400';
    if (status === 'failed') return 'bg-red-900/40 text-red-400';
    if (status === 'running') return 'bg-blue-900/40 text-blue-400';
    return 'bg-orange-900/40 text-orange-400';
  }
</script>

<svelte:head>
  <title>Houdini — Sessions</title>
</svelte:head>

<div class="min-h-screen p-4 max-w-6xl mx-auto">
  <h1 class="text-xl font-bold text-blue-400 mb-4">Sessions</h1>

  <div class="bg-card border border-border rounded-lg p-4">
    <table class="w-full text-left">
      <thead class="text-xs uppercase text-gray-400">
        <tr>
          <th class="pb-2">ID</th>
          <th class="pb-2">Task</th>
          <th class="pb-2">Architecture</th>
          <th class="pb-2">Status</th>
          <th class="pb-2">Duration</th>
          <th class="pb-2">Actions</th>
        </tr>
      </thead>
      <tbody class="text-sm">
        {#each $tasks as task (task.task_id)}
          <tr class="border-t border-border hover:bg-[#0d1117]">
            <td class="py-2 font-mono text-xs text-gray-400">{task.task_id}</td>
            <td class="py-2 max-w-xs truncate">{task.task}</td>
            <td class="py-2 text-xs text-gray-400">{task.architecture}</td>
            <td class="py-2">
              <span class="text-[10px] px-2 py-0.5 rounded {statusColor(task.status)}">{task.status}</span>
            </td>
            <td class="py-2 text-xs text-gray-400">{task.duration_s != null ? `${task.duration_s.toFixed(1)}s` : '—'}</td>
            <td class="py-2">
              <a
                href="/"
                on:click|preventDefault={() => selectedTaskId.set(task.task_id)}
                class="text-blue-400 hover:underline text-xs"
              >
                View
              </a>
            </td>
          </tr>
        {:else}
          <tr>
            <td colspan="6" class="py-4 text-gray-500 italic text-sm">No sessions yet.</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>
