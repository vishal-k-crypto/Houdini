<script lang="ts">
  import { onMount } from 'svelte';
  import { detectProviders, testProvider, pullOllamaModel, ONBOARDING_STEPS } from '$lib/onboarding';
  import type { DetectedProvider } from '$lib/onboarding';
  import { settings, saveSettings } from '$lib/store';

  let step = 0;
  let detected: DetectedProvider[] = [];
  let loading = false;
  let error = '';
  let activeProvider = 'openai';
  let modelInput = 'gpt-4o';
  let apiKeyInput = '';
  let apiBaseInput = '';
  let ollamaModelToPull = '';
  let pullingModel = false;
  let pullSuccessMessage = '';

  let testResult: { success: boolean; message?: string; error?: string } | null = null;
  let testing = false;

  onMount(async () => {
    await loadDetection();
    // Default form configuration based on current settings
    if ($settings) {
      activeProvider = $settings.provider || 'openai';
      modelInput = $settings.model || 'gpt-4o';
      apiKeyInput = $settings.api_key || '';
      apiBaseInput = $settings.api_base || '';
    }
  });

  async function loadDetection() {
    loading = true;
    error = '';
    try {
      detected = await detectProviders();
    } catch (e: any) {
      error = e.message || String(e);
    } finally {
      loading = false;
    }
  }

  function handleProviderChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    activeProvider = target.value;
    // Set sensible defaults for models
    if (activeProvider === 'openai') modelInput = 'gpt-4o';
    else if (activeProvider === 'anthropic') modelInput = 'claude-3-5-sonnet-20240620';
    else if (activeProvider === 'gemini') modelInput = 'gemini-2.0-flash-exp';
    else if (activeProvider === 'deepseek') modelInput = 'deepseek-chat';
    else if (activeProvider === 'grok') modelInput = 'grok-2-latest';
    else if (activeProvider === 'openrouter') modelInput = 'openrouter/anthropic/claude-3.5-sonnet';
    else if (activeProvider === 'ollama') {
      const ollamaDev = detected.find(p => p.id === 'ollama');
      modelInput = ollamaDev?.models?.[0] || 'qwen2.5-coder:7b';
    } else if (activeProvider === 'cli') {
      const cliDev = detected.find(p => p.id === 'cli');
      const firstAgent = cliDev?.agents ? Object.keys(cliDev.agents)[0] : '';
      modelInput = firstAgent || 'claude';
    }
  }

  async function runConnectionTest() {
    testing = true;
    testResult = null;
    error = '';
    try {
      const res = await testProvider(activeProvider, modelInput, apiKeyInput, apiBaseInput);
      testResult = res;
    } catch (e: any) {
      testResult = { success: false, error: e.message || String(e) };
    } finally {
      testing = false;
    }
  }

  async function handlePullOllamaModel() {
    if (!ollamaModelToPull.trim()) return;
    pullingModel = true;
    pullSuccessMessage = '';
    error = '';
    try {
      await pullOllamaModel(ollamaModelToPull.trim());
      pullSuccessMessage = `Successfully queued pulling of model '${ollamaModelToPull}'. It is downloading in the background.`;
      ollamaModelToPull = '';
      // Reload detection after a brief delay to see if models refreshed
      setTimeout(loadDetection, 5000);
    } catch (e: any) {
      error = e.message || String(e);
    } finally {
      pullingModel = false;
    }
  }

  async function handleSaveConfig() {
    loading = true;
    error = '';
    try {
      const updatedSettings = {
        ...$settings,
        provider: activeProvider,
        model: modelInput,
        api_key: apiKeyInput,
        api_base: apiBaseInput,
        use_enhanced: true,
        smart_router_enabled: true
      };
      await saveSettings(updatedSettings);
      window.location.href = '/';
    } catch (e: any) {
      error = e.message || String(e);
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Houdini — Setup Wizard</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center p-4 bg-[#090d13]">
  <div class="w-full max-w-2xl bg-card border border-border rounded-xl shadow-2xl overflow-hidden backdrop-blur-md">
    <!-- Header -->
    <div class="p-6 border-b border-border bg-[#0d1117] flex justify-between items-center">
      <div>
        <h1 class="text-xl font-bold text-blue-400">Houdini Onboarding Wizard</h1>
        <p class="text-xs text-gray-400 mt-1">Configure your AI engine persistently in a few clicks.</p>
      </div>
      <span class="text-xs font-semibold px-2.5 py-1 rounded bg-blue-900/30 text-blue-400 border border-blue-800/50">
        Step {step + 1} of 4
      </span>
    </div>

    <!-- Progress indicator -->
    <div class="flex h-1 bg-[#161b22]">
      {#each ONBOARDING_STEPS as _, i}
        <div class="flex-1 transition-all duration-300 {i <= step ? 'bg-blue-500' : 'bg-transparent'}"></div>
      {/each}
    </div>

    <!-- Content -->
    <div class="p-6 space-y-6 min-h-[320px]">
      {#if step === 0}
        <!-- Step 1: Deep scan / Detection -->
        <div class="space-y-4">
          <div>
            <h2 class="text-sm font-semibold text-gray-200">System Deep Scan</h2>
            <p class="text-xs text-gray-400">Here are the AI providers and tools currently detected on your local system:</p>
          </div>

          {#if loading}
            <div class="flex flex-col items-center justify-center py-12 space-y-3">
              <div class="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
              <span class="text-xs text-gray-400">Scanning host system...</span>
            </div>
          {:else}
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              {#each detected as p}
                <div class="p-3 border rounded-lg bg-[#0d1117]/60 flex flex-col justify-between {p.available ? 'border-green-900/50 bg-green-950/5' : 'border-border'}">
                  <div class="flex items-center justify-between">
                    <span class="text-sm font-bold capitalize text-gray-200">{p.id}</span>
                    {#if p.available}
                      <span class="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-green-900/40 text-green-400">Detected</span>
                    {:else}
                      <span class="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">Not configured</span>
                    {/if}
                  </div>
                  <div class="mt-2 text-xs text-gray-400">
                    {#if p.id === 'ollama'}
                      {#if p.available && p.models && p.models.length > 0}
                        <span class="text-blue-400">{p.models.length} models pulled</span>
                      {:else if p.available}
                        <span class="text-orange-400">Running, but no models found</span>
                      {:else}
                        <span>Local Ollama server is offline</span>
                      {/if}
                    {:else if p.id === 'cli'}
                      {#if p.available && p.agents}
                        <span class="text-blue-400">{Object.keys(p.agents).join(', ')} on PATH</span>
                      {:else}
                        <span>No CLI coding agents found in PATH</span>
                      {/if}
                    {:else}
                      <span>Requires {p.source || 'API Key'}</span>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}

          <div class="p-3 bg-blue-950/20 border border-blue-900/40 rounded-lg text-xs text-blue-300">
            <strong>Tip:</strong> If you use local CLI tools like Claude Code or Codex, they are automatically detected on PATH and can be routed coding tasks dynamically by the Smart Router!
          </div>
        </div>

      {:else if step === 1}
        <!-- Step 2: Configure selected provider -->
        <div class="space-y-4">
          <div>
            <h2 class="text-sm font-semibold text-gray-200">Configure AI Engine</h2>
            <p class="text-xs text-gray-400">Select the provider you wish to use as your default engine:</p>
          </div>

          <div class="space-y-3">
            <div>
              <label class="block text-xs uppercase text-gray-400 mb-1">Select Provider</label>
              <select
                value={activeProvider}
                on:change={handleProviderChange}
                class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm text-gray-200 focus:border-blue-500 outline-none"
              >
                <option value="openai">OpenAI (GPT-4o, etc.)</option>
                <option value="anthropic">Anthropic (Claude 3.5, etc.)</option>
                <option value="gemini">Google Gemini</option>
                <option value="deepseek">DeepSeek API</option>
                <option value="grok">xAI Grok</option>
                <option value="openrouter">OpenRouter</option>
                <option value="ollama">Ollama (Local Models)</option>
                <option value="cli">Local CLI Coding Agent</option>
                <option value="webllm">WebLLM (In-Browser Inference)</option>
              </select>
            </div>

            <!-- API Key Input -->
            {#if ['openai', 'anthropic', 'gemini', 'deepseek', 'grok', 'openrouter'].includes(activeProvider)}
              <div>
                <label class="block text-xs uppercase text-gray-400 mb-1">API Key</label>
                <input
                  type="password"
                  bind:value={apiKeyInput}
                  placeholder="Enter API key"
                  class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm text-gray-200 focus:border-blue-500 outline-none font-mono"
                />
              </div>

              <div>
                <label class="block text-xs uppercase text-gray-400 mb-1">API Base URL (Optional)</label>
                <input
                  type="text"
                  bind:value={apiBaseInput}
                  placeholder="Defaults to official endpoint"
                  class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm text-gray-200 focus:border-blue-500 outline-none"
                />
              </div>
            {/if}

            <!-- Ollama details / pull model -->
            {#if activeProvider === 'ollama'}
              <div>
                <label class="block text-xs uppercase text-gray-400 mb-1">Ollama API Endpoint</label>
                <input
                  type="text"
                  bind:value={apiBaseInput}
                  placeholder="http://localhost:11434"
                  class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm text-gray-200 focus:border-blue-500 outline-none"
                />
              </div>

              <!-- Pulled models list -->
              {@const ollamaDev = detected.find(p => p.id === 'ollama')}
              {#if ollamaDev && ollamaDev.available && ollamaDev.models && ollamaDev.models.length > 0}
                <div>
                  <label class="block text-xs uppercase text-gray-400 mb-1">Available Models</label>
                  <select
                    bind:value={modelInput}
                    class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm text-gray-200 focus:border-blue-500 outline-none"
                  >
                    {#each ollamaDev.models as m}
                      <option value={m}>{m}</option>
                    {/each}
                  </select>
                </div>
              {/if}

              <!-- Pull model input -->
              <div class="p-4 border border-border rounded-lg bg-[#0d1117]/40 space-y-2">
                <label class="block text-xs uppercase text-gray-400">Download a new local model</label>
                <div class="flex gap-2">
                  <input
                    type="text"
                    bind:value={ollamaModelToPull}
                    placeholder="e.g. qwen2.5-coder:7b"
                    class="flex-1 bg-[#0d1117] border border-border rounded px-2.5 py-1 text-sm text-gray-200 focus:border-blue-500 outline-none"
                  />
                  <button
                    on:click={handlePullOllamaModel}
                    disabled={pullingModel || !ollamaModelToPull.trim()}
                    class="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded text-xs font-semibold"
                  >
                    {pullingModel ? 'Pulling...' : 'Pull'}
                  </button>
                </div>
                {#if pullSuccessMessage}
                  <p class="text-[10px] text-green-400 mt-1">{pullSuccessMessage}</p>
                {/if}
              </div>
            {/if}

            <!-- CLI agent selection -->
            {#if activeProvider === 'cli'}
              {@const cliDev = detected.find(p => p.id === 'cli')}
              {#if cliDev && cliDev.available && cliDev.agents}
                <div>
                  <label class="block text-xs uppercase text-gray-400 mb-1">Select Installed Agent</label>
                  <select
                    bind:value={modelInput}
                    class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm text-gray-200 focus:border-blue-500 outline-none"
                  >
                    {#each Object.entries(cliDev.agents) as [name, info]}
                      <option value={name}>{info.description} ({info.command})</option>
                    {/each}
                  </select>
                </div>
              {:else}
                <div class="p-3 bg-red-950/20 border border-red-900/40 rounded-lg text-xs text-red-300">
                  No CLI coding agents detected on PATH. Make sure tools like Claude Code are installed globally.
                </div>
              {/if}
            {/if}

            <!-- Model Input (except Ollama / CLI dropdowns) -->
            {#if !['ollama', 'cli', 'webllm'].includes(activeProvider)}
              <div>
                <label class="block text-xs uppercase text-gray-400 mb-1">Model Name</label>
                <input
                  type="text"
                  bind:value={modelInput}
                  placeholder="Enter model identifier"
                  class="w-full bg-[#0d1117] border border-border rounded p-2 text-sm text-gray-200 focus:border-blue-500 outline-none font-mono"
                />
              </div>
            {/if}

            {#if activeProvider === 'webllm'}
              <div class="p-3 bg-blue-950/20 border border-blue-900/40 rounded-lg text-xs text-blue-300 space-y-1">
                <p class="font-semibold">WebLLM runs in-browser:</p>
                <p>Loads model weights directly into your browser's WebGPU context. Extremely local, no API keys or local executables required.</p>
                <p class="mt-2 text-gray-400">Select model size:</p>
                <select bind:value={modelInput} class="w-full bg-[#0d1117] border border-border rounded p-1 text-xs text-gray-200">
                  <option value="Llama-3.2-1B-Instruct-q4f32_1-MLC">Llama 3.2 1B (Ultra-fast)</option>
                  <option value="Llama-3.1-8B-Instruct-q4f32_1-MLC">Llama 3.1 8B (Recommended)</option>
                  <option value="Qwen2.5-7B-Instruct-q4f16_1-MLC">Qwen 2.5 7B (Coding expert)</option>
                </select>
              </div>
            {/if}
          </div>
        </div>

      {:else if step === 2}
        <!-- Step 3: Test Connection -->
        <div class="space-y-4">
          <div>
            <h2 class="text-sm font-semibold text-gray-200">Verify Connectivity</h2>
            <p class="text-xs text-gray-400">We will verify connection using your configured provider and model:</p>
          </div>

          <div class="p-4 border border-border rounded-lg bg-[#0d1117] space-y-2">
            <div class="flex justify-between text-xs text-gray-400">
              <span>Provider:</span>
              <span class="font-bold text-gray-200 capitalize">{activeProvider}</span>
            </div>
            <div class="flex justify-between text-xs text-gray-400">
              <span>Model:</span>
              <span class="font-bold text-gray-200 font-mono">{modelInput}</span>
            </div>
            {#if apiBaseInput}
              <div class="flex justify-between text-xs text-gray-400">
                <span>Base URL:</span>
                <span class="font-bold text-gray-200">{apiBaseInput}</span>
              </div>
            {/if}
          </div>

          <div class="flex flex-col items-center justify-center py-6 space-y-3">
            <button
              on:click={runConnectionTest}
              disabled={testing}
              class="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded font-semibold text-sm transition-all"
            >
              {testing ? 'Testing connection...' : 'Test Connection'}
            </button>

            {#if testResult}
              <div class="w-full p-3 border rounded-lg text-xs mt-4 {testResult.success ? 'border-green-900/50 bg-green-950/10 text-green-300' : 'border-red-900/50 bg-red-950/10 text-red-300'}">
                {#if testResult.success}
                  <div class="font-bold mb-1">✓ Connection Successful!</div>
                  <p class="text-[11px] text-gray-300 font-mono">{testResult.message}</p>
                {:else}
                  <div class="font-bold mb-1">✗ Connection Failed</div>
                  <p class="text-[11px] text-red-400">{testResult.error || 'Check your API keys and parameters.'}</p>
                {/if}
              </div>
            {/if}
          </div>
        </div>

      {:else}
        <!-- Step 4: Finish/Apply -->
        <div class="space-y-4 text-center py-8">
          <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-900/30 text-green-400 border border-green-800/50 mb-3 animate-pulse">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
            </svg>
          </div>

          <h2 class="text-lg font-bold text-gray-100">Setup Complete!</h2>
          <p class="text-xs text-gray-400 max-w-md mx-auto">
            Houdini has persisted your default configurations into the backend <code class="font-mono text-blue-300">.env</code> file.
            The Smart Router is active and will orchestrate local and frontier models automatically.
          </p>

          <div class="p-3 border border-border bg-[#0d1117] rounded-lg max-w-sm mx-auto text-left space-y-1 text-[11px] text-gray-400">
            <div class="flex justify-between"><span class="font-semibold text-gray-300">Default engine:</span> <span class="font-mono capitalize">{activeProvider}</span></div>
            <div class="flex justify-between"><span class="font-semibold text-gray-300">Default model:</span> <span class="font-mono">{modelInput}</span></div>
            <div class="flex justify-between"><span class="font-semibold text-gray-300">Smart routing:</span> <span class="text-green-400">Active</span></div>
          </div>
        </div>
      {/if}
    </div>

    <!-- Footer -->
    <div class="p-4 border-t border-border bg-[#0d1117] flex justify-between">
      {#if step > 0 && step < 3}
        <button
          on:click={() => step = step - 1}
          class="px-4 py-1.5 border border-border text-gray-300 hover:bg-[#161b22] rounded text-sm transition-colors"
        >
          Back
        </button>
      {:else}
        <div></div>
      {/if}

      {#if step < 2}
        <button
          on:click={() => step = step + 1}
          class="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-semibold transition-colors"
        >
          Next
        </button>
      {:else if step === 2}
        <button
          on:click={() => step = step + 1}
          disabled={!testResult?.success}
          class="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded text-sm font-semibold transition-colors"
        >
          Confirm & Save
        </button>
      {:else}
        <button
          on:click={handleSaveConfig}
          disabled={loading}
          class="px-5 py-1.5 bg-green-600 hover:bg-green-500 text-white rounded text-sm font-bold transition-colors"
        >
          {loading ? 'Saving...' : 'Finish Setup'}
        </button>
      {/if}
    </div>
  </div>
</div>

<style>
  /* Glassmorphism styling overrides */
  .bg-card {
    background-color: rgba(22, 27, 34, 0.7);
    backdrop-filter: blur(10px);
  }
</style>
