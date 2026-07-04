<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    settings,
    fetchBenchmarkTasks,
    startBenchmarkRun,
    fetchBenchmarkResult,
    fetchProviders,
    type BenchmarkTask,
    type BenchmarkReport,
    type ProviderInfo
  } from '$lib/store';

  let tasks: BenchmarkTask[] = [];
  let providers: ProviderInfo[] = [];
  let tagFilter = '';
  let query = '';
  let loading = true;
  let error = '';

  let architecture = $settings.architecture || 'adaptive';
  let provider = $settings.provider || '';
  let model = $settings.model || '';
  let verifyWithLlm = false;
  let running = false;
  let runError = '';
  let currentRunId: string | null = null;
  let currentReport: BenchmarkReport | null = null;
  let pollInterval: number;

  async function load() {
    loading = true;
    error = '';
    try {
      const [t, p] = await Promise.all([
        fetchBenchmarkTasks(tagFilter || undefined, query || undefined),
        fetchProviders()
      ]);
      tasks = t;
      providers = p;
    } catch (e: any) {
      error = e.message || String(e);
    } finally {
      loading = false;
    }
  }

  async function startRun() {
    running = true;
    runError = '';
    currentReport = null;
    try {
      const info = await startBenchmarkRun({
        architecture,
        provider: provider || undefined,
        model: model || undefined,
        verify_with_llm: verifyWithLlm
      });
      currentRunId = info.run_id;
      pollInterval = window.setInterval(pollRun, 2000);
    } catch (e: any) {
      runError = e.message || String(e);
      running = false;
    }
  }

  async function pollRun() {
    if (!currentRunId) return;
    try {
      const info = await fetchBenchmarkResult(currentRunId);
      if (info.status === 'complete' && info.report) {
        currentReport = info.report;
        running = false;
        window.clearInterval(pollInterval);
      }
    } catch (e: any) {
      runError = e.message || String(e);
      running = false;
      window.clearInterval(pollInterval);
    }
  }

  onMount(() => {
    load();
  });

  onDestroy(() => {
    window.clearInterval(pollInterval);
  });

  function statusColor(success: boolean) {
    return success ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400';
  }

  function uniqueTags(ts: BenchmarkTask[]) {
    const set = new Set<string>();
    ts.forEach((t) => t.tags.forEach((tag) => set.add(tag)));
    return Array.from(set).sort();
  }

  $: filteredTasks = tasks.filter((t) => {
    const matchesTag = !tagFilter || t.tags.includes(tagFilter);
    const matchesQuery = !query || t.description.toLowerCase().includes(query.toLowerCase()) || t.id.toLowerCase().includes(query.toLowerCase());
    return matchesTag && matchesQuery;
  });
</script>

<svelte:head>
  <title>Houdini — Benchmarks</title>
</svelte:head>

<div class="min-h-screen p-4 max-w-6xl mx-auto">
  <h1 class="text-xl font-bold text-blue-400 mb-4">Benchmarks</h1>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
    <div class="bg-card border border-border rounded-lg p-4 lg:col-span-2">
      <h2 class="text-xs uppercase text-gray-400 mb-3">Run Benchmark Suite</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <div>
          <label for="bench-arch" class="text-[10px] uppercase text-gray-500 block mb-1">Architecture</label>
          <select id="bench-arch" bind:value={architecture} class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm">
            <option value="adaptive">Adaptive</option>
            <option value="langgraph">LangGraph</option>
            <option value="legacy">Legacy</option>
          </select>
        </div>
        <div>
          <label for="bench-provider" class="text-[10px] uppercase text-gray-500 block mb-1">Provider</label>
          <select id="bench-provider" bind:value={provider} class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm">
            <option value="">Default</option>
            {#each providers as p (p.id)}
              <option value={p.id}>{p.id}{p.available ? '' : ' (unavailable)'}</option>
            {/each}
          </select>
        </div>
        <div>
          <label for="bench-model" class="text-[10px] uppercase text-gray-500 block mb-1">Model</label>
          <input id="bench-model" bind:value={model} placeholder="e.g. qwen3-coder:480b-cloud" class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm" />
        </div>
        <div class="flex items-end">
          <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
            <input type="checkbox" bind:checked={verifyWithLlm} class="rounded border-border" />
            Verify outcomes with LLM judge
          </label>
        </div>
      </div>
      <button
        on:click={startRun}
        disabled={running || tasks.length === 0}
        class="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm font-semibold"
      >
        {running ? 'Running…' : `Run ${tasks.length} benchmark tasks`}
      </button>
      {#if runError}
        <p class="text-red-400 text-xs mt-2">{runError}</p>
      {/if}
    </div>

    <div class="bg-card border border-border rounded-lg p-4">
      <h2 class="text-xs uppercase text-gray-400 mb-3">Filter Tasks</h2>
      <div class="space-y-3">
        <div>
          <label for="bench-tag" class="text-[10px] uppercase text-gray-500 block mb-1">Tag</label>
          <select id="bench-tag" bind:value={tagFilter} class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm">
            <option value="">All tags</option>
            {#each uniqueTags(tasks) as tag (tag)}
              <option value={tag}>{tag}</option>
            {/each}
          </select>
        </div>
        <div>
          <label for="bench-query" class="text-[10px] uppercase text-gray-500 block mb-1">Search</label>
          <input id="bench-query" bind:value={query} placeholder="Task description…" class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm" />
        </div>
      </div>
    </div>
  </div>

  {#if currentReport}
    <div class="bg-card border border-border rounded-lg p-4 mb-6">
      <div class="flex justify-between items-center mb-3">
        <h2 class="text-xs uppercase text-gray-400">Latest Report: {currentReport.run_id}</h2>
        <span class="text-[10px] px-2 py-0.5 rounded {currentReport.success_rate >= 80 ? 'bg-green-900/40 text-green-400' : currentReport.success_rate >= 50 ? 'bg-orange-900/40 text-orange-400' : 'bg-red-900/40 text-red-400'}">
          {currentReport.success_rate.toFixed(1)}% success
        </span>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <div class="bg-[#0d1117] border border-border rounded p-3">
          <p class="text-[10px] text-gray-500 uppercase">Total</p>
          <p class="text-lg font-semibold text-gray-200">{currentReport.total_tasks}</p>
        </div>
        <div class="bg-[#0d1117] border border-border rounded p-3">
          <p class="text-[10px] text-gray-500 uppercase">Passed</p>
          <p class="text-lg font-semibold text-green-400">{currentReport.passed}</p>
        </div>
        <div class="bg-[#0d1117] border border-border rounded p-3">
          <p class="text-[10px] text-gray-500 uppercase">Failed</p>
          <p class="text-lg font-semibold text-red-400">{currentReport.failed}</p>
        </div>
        <div class="bg-[#0d1117] border border-border rounded p-3">
          <p class="text-[10px] text-gray-500 uppercase">Avg Duration</p>
          <p class="text-lg font-semibold text-gray-200">{currentReport.avg_duration_s.toFixed(1)}s</p>
        </div>
      </div>

      {#if Object.keys(currentReport.tag_breakdown).length > 0}
        <h3 class="text-[10px] uppercase text-gray-500 mb-2">Tag Breakdown</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-4">
          {#each Object.entries(currentReport.tag_breakdown) as [tag, info] (tag)}
            <div class="bg-[#0d1117] border border-border rounded p-2">
              <div class="flex justify-between items-center">
                <span class="text-xs text-gray-300">{tag}</span>
                <span class="text-[10px] {info.success_rate >= 80 ? 'text-green-400' : info.success_rate >= 50 ? 'text-orange-400' : 'text-red-400'}">{info.passed}/{info.total} ({info.success_rate}%)</span>
              </div>
              <p class="text-[10px] text-gray-500 mt-1">avg {info.avg_duration_s}s</p>
            </div>
          {/each}
        </div>
      {/if}

      <h3 class="text-[10px] uppercase text-gray-500 mb-2">Results</h3>
      <div class="space-y-2 max-h-96 overflow-y-auto">
        {#each currentReport.results as result (result.task_id)}
          <div class="bg-[#0d1117] border border-border rounded p-3">
            <div class="flex justify-between items-start">
              <div>
                <p class="text-xs font-mono text-gray-400">{result.task_id}</p>
                <p class="text-sm text-gray-200 mt-0.5">{result.description}</p>
              </div>
              <span class="text-[10px] px-2 py-0.5 rounded {statusColor(result.success)}">{result.success ? 'PASS' : 'FAIL'}</span>
            </div>
            <div class="flex flex-wrap gap-2 mt-2">
              {#each result.tags as tag (tag)}
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-[#161b22] text-gray-500">#{tag}</span>
              {/each}
            </div>
            <div class="flex flex-wrap gap-4 mt-2 text-[10px] text-gray-500">
              <span>Duration: {result.duration_s.toFixed(1)}s</span>
              <span>Confidence: {result.avg_confidence.toFixed(1)}</span>
              {#if result.vision_strategy}<span>Vision: {result.vision_strategy}</span>{/if}
              {#if result.judge_score !== undefined}<span>Judge: {result.judge_score.toFixed(2)}</span>{/if}
            </div>
            {#if result.error}
              <p class="text-[10px] text-red-400 mt-2">{result.error}</p>
            {/if}
            {#if result.judge_reason}
              <p class="text-[10px] text-gray-400 mt-1">Judge: {result.judge_reason}</p>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <div class="bg-card border border-border rounded-lg p-4">
    <div class="flex justify-between items-center mb-3">
      <h2 class="text-xs uppercase text-gray-400">Benchmark Tasks</h2>
      <span class="text-[10px] text-gray-500">{filteredTasks.length} shown</span>
    </div>
    {#if loading}
      <p class="text-sm text-gray-400">Loading tasks…</p>
    {:else if error}
      <p class="text-red-400 text-sm">{error}</p>
    {:else}
      <div class="space-y-2 max-h-[32rem] overflow-y-auto">
        {#each filteredTasks as task (task.id)}
          <div class="bg-[#0d1117] border border-border rounded p-3">
            <div class="flex justify-between items-start">
              <p class="text-xs font-mono text-gray-400">{task.id}</p>
              <span class="text-[10px] text-gray-500">{task.timeout_s}s</span>
            </div>
            <p class="text-sm text-gray-200 mt-0.5">{task.description}</p>
            <div class="flex flex-wrap gap-2 mt-2">
              {#each task.tags as tag (tag)}
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-[#161b22] text-gray-500">#{tag}</span>
              {/each}
            </div>
            {#if task.verify_hint}
              <p class="text-[10px] text-gray-500 mt-2">Hint: {task.verify_hint}</p>
            {/if}
          </div>
        {:else}
          <p class="text-sm text-gray-500 italic">No benchmark tasks match.</p>
        {/each}
      </div>
    {/if}
  </div>
</div>
