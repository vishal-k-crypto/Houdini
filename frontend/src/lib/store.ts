import { writable, derived, type Readable } from 'svelte/store';
import type { Writable } from 'svelte/store';

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Task {
  task_id: string;
  task: string;
  status: TaskStatus;
  architecture: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_s?: number;
  result?: Record<string, any>;
  events?: Array<Record<string, any>>;
  confidence_scores?: Array<Record<string, any>>;
}

export interface Health {
  status: string;
  uptime_s: number;
  tasks_total: number;
  tasks_running: number;
  tasks_completed: number;
  tasks_failed: number;
}

export interface Settings {
  provider: string;
  model: string;
  api_key: string;
  api_base: string;
  architecture: 'adaptive' | 'langgraph' | 'legacy';
  use_enhanced: boolean;
  thinking_window: boolean;
  checkpoint_path: string;
  smart_router_enabled: boolean;
  smart_router_prefer_local: boolean;
  smart_router_budget_cap_usd: string;
  smart_router_latency_budget_ms: string;
  use_browser_vision: boolean;
  [key: string]: any;
}

export interface ProviderInfo {
  id: string;
  name: string;
  available: boolean;
  requires_api_key?: boolean;
  is_local?: boolean;
  models?: string[];
}

export interface BenchmarkTask {
  id: string;
  description: string;
  tags: string[];
  expected_app?: string;
  timeout_s: number;
  verify_hint?: string;
}

export interface BenchmarkResult {
  task_id: string;
  description: string;
  tags: string[];
  success: boolean;
  error?: string;
  duration_s: number;
  vision_strategy?: string;
  avg_confidence: number;
  judge_score?: number;
  judge_reason?: string;
}

export interface BenchmarkReport {
  run_id: string;
  started_at: string;
  completed_at?: string;
  total_tasks: number;
  passed: number;
  failed: number;
  skipped: number;
  success_rate: number;
  avg_duration_s: number;
  median_duration_s: number;
  avg_confidence: number;
  results: BenchmarkResult[];
  tag_breakdown: Record<string, { total: number; passed: number; success_rate: number; avg_duration_s: number }>;
}

export interface BenchmarkRunInfo {
  run_id: string;
  tasks: number;
  status: 'started' | 'running' | 'complete';
  report?: BenchmarkReport;
}

export interface SessionEvent {
  type: string;
  task_id?: string;
  ts?: string;
  [key: string]: any;
}

export interface ScreenshotEvent {
  task_id?: string;
  image_base64?: string;
  timestamp?: string;
}

export interface TerminalEntry {
  ts: string;
  text: string;
}

export const tasks = writable<Task[]>([]);
export const health = writable<Health | null>(null);
export const wsConnected = writable(false);
export const terminal = writable<TerminalEntry[]>([]);
export const screenshots = writable<ScreenshotEvent[]>([]);
export const events = writable<SessionEvent[]>([]);
export const selectedTaskId = writable<string | null>(null);

export const selectedTask: Readable<Task | null> = derived(
  [tasks, selectedTaskId],
  ([$tasks, $id]) => $tasks.find((t) => t.task_id === $id) || null
);

export function appendTerminal(text: string) {
  const ts = new Date().toLocaleTimeString();
  terminal.update((log) => [{ ts, text }, ...log].slice(0, 400));
}

export function appendEvent(event: SessionEvent) {
  events.update((arr) => [event, ...arr].slice(0, 500));
}

export function appendScreenshot(ev: ScreenshotEvent) {
  screenshots.update((arr) => [ev, ...arr].slice(0, 20));
}

export async function submitTask(
  task: string,
  opts: Partial<{
    provider: string;
    model: string;
    architecture: 'adaptive' | 'langgraph' | 'legacy';
    use_enhanced: boolean;
    cloud_endpoint: string;
    checkpoint_path: string;
  }> = {}
) {
  const res = await fetch(`/api/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, ...opts })
  });
  if (!res.ok) throw new Error(`Failed to submit task: ${res.status}`);
  const t = (await res.json()) as Task;
  tasks.update((arr) => [t, ...arr]);
  selectedTaskId.set(t.task_id);
  return t;
}

export async function fetchTasks() {
  const res = await fetch(`/api/tasks?limit=50`);
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.status}`);
  const data = (await res.json()) as { tasks: Task[] };
  tasks.update((arr) => {
    const map = new Map<string, Task>(arr.map((t) => [t.task_id, t]));
    data.tasks.forEach((t) => {
      const existing = map.get(t.task_id);
      map.set(t.task_id, existing ? { ...existing, ...t } : t);
    });
    return Array.from(map.values()).sort((a, b) => b.created_at.localeCompare(a.created_at));
  });
}

export async function fetchTask(id: string) {
  const res = await fetch(`/api/tasks/${id}`);
  if (!res.ok) return;
  const t = (await res.json()) as Task;
  tasks.update((arr) => {
    const idx = arr.findIndex((x) => x.task_id === id);
    if (idx >= 0) {
      arr[idx] = t;
    } else {
      arr.push(t);
    }
    return arr.sort((a, b) => b.created_at.localeCompare(a.created_at));
  });
}

export async function fetchHealth() {
  const res = await fetch(`/api/health`);
  if (!res.ok) return;
  health.set((await res.json()) as Health);
}

export async function fetchProviders(): Promise<ProviderInfo[]> {
  const res = await fetch(`/api/providers`);
  if (!res.ok) throw new Error(`Failed to fetch providers: ${res.status}`);
  return ((await res.json()) as { providers: ProviderInfo[] }).providers;
}

export async function fetchSettings(): Promise<Settings> {
  const res = await fetch(`/api/settings`);
  if (!res.ok) throw new Error(`Failed to fetch settings: ${res.status}`);
  return (await res.json()) as Settings;
}

function _providerEnvKey(providerId: string): string | undefined {
  const base = providerId.split(':')[0].toLowerCase();
  const map: Record<string, string> = {
    openai: 'OPENAI_API_KEY',
    anthropic: 'ANTHROPIC_API_KEY',
    gemini: 'GEMINI_API_KEY',
    deepseek: 'DEEPSEEK_API_KEY',
    grok: 'GROK_API_KEY',
    openrouter: 'OPENROUTER_API_KEY'
  };
  return map[base];
}

export async function saveSettings(settings: Settings): Promise<Settings> {
  const payload: Record<string, any> = {
    default_provider: settings.provider || undefined,
    model: settings.model || undefined,
    api_base: settings.api_base || undefined,
    smart_router_enabled: settings.smart_router_enabled,
    smart_router_prefer_local: settings.smart_router_prefer_local,
    smart_router_budget_cap_usd: settings.smart_router_budget_cap_usd || undefined,
    smart_router_latency_budget_ms: settings.smart_router_latency_budget_ms || undefined,
    use_browser_vision: settings.use_browser_vision
  };
  if (settings.provider && settings.api_key) {
    const envKey = _providerEnvKey(settings.provider);
    if (envKey) {
      payload.provider_keys = { [envKey]: settings.api_key };
    }
  }
  if (settings.provider && settings.model) {
    payload.provider_models = { [settings.provider]: settings.model };
  }
  if (settings.provider && settings.api_base) {
    payload.provider_base_urls = { [settings.provider]: settings.api_base };
  }
  const res = await fetch(`/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error(`Failed to save settings: ${res.status}`);
  return (await res.json()) as Settings;
}

export async function fetchBenchmarkTasks(tag?: string, query?: string): Promise<BenchmarkTask[]> {
  const params = new URLSearchParams();
  if (tag) params.set('tag', tag);
  if (query) params.set('task', query);
  const res = await fetch(`/api/benchmarks/tasks?${params.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch benchmark tasks: ${res.status}`);
  const data = (await res.json()) as { tasks: BenchmarkTask[] };
  return data.tasks;
}

export async function startBenchmarkRun(opts: {
  tag?: string;
  task_id?: string;
  architecture?: string;
  provider?: string;
  model?: string;
  cloud_endpoint?: string;
  verify_with_llm?: boolean;
}): Promise<BenchmarkRunInfo> {
  const res = await fetch(`/api/benchmarks/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts)
  });
  if (!res.ok) throw new Error(`Failed to start benchmark: ${res.status}`);
  return (await res.json()) as BenchmarkRunInfo;
}

export async function fetchBenchmarkResult(runId: string): Promise<BenchmarkRunInfo> {
  const res = await fetch(`/api/benchmarks/results/${runId}`);
  if (!res.ok) throw new Error(`Failed to fetch benchmark result: ${res.status}`);
  return (await res.json()) as BenchmarkRunInfo;
}

export async function generateSkillFromFailure(task: string, error?: string): Promise<{ skill_id: string; path: string; skill_text: string }> {
  const res = await fetch(`/api/skills/generate-from-failure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, error: error || '' })
  });
  if (!res.ok) throw new Error(`Failed to generate skill: ${res.status}`);
  return (await res.json()) as { skill_id: string; path: string; skill_text: string };
}

export function connectWebSocket() {
  const wsUrl = getWsUrl();
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    wsConnected.set(true);
    appendTerminal('WebSocket connected');
  };

  ws.onclose = () => {
    wsConnected.set(false);
    appendTerminal('WebSocket disconnected');
  };

  ws.onerror = () => {
    wsConnected.set(false);
    appendTerminal('WebSocket error');
  };

  ws.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as SessionEvent;
      appendEvent(event);

      if (event.type === 'screenshot') {
        appendScreenshot(event as ScreenshotEvent);
      } else if (event.type === 'terminal') {
        appendTerminal((event as any).text || JSON.stringify(event));
      } else if (event.type === 'confidence') {
        if (event.task_id) fetchTask(event.task_id);
      }

      if (event.task_id) {
        fetchTask(event.task_id).catch(() => {});
      }
    } catch (e) {
      appendTerminal('WebSocket message parse error');
    }
  };

  return ws;
}

function getWsUrl() {
  if (typeof window === 'undefined') return '';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

export function persistSettings(): Writable<Settings> {
  const key = 'houdini.settings';
  const initial: Settings = {
    provider: 'ollama',
    model: 'qwen3-coder:480b-cloud',
    api_key: '',
    api_base: '',
    architecture: 'adaptive',
    use_enhanced: true,
    thinking_window: false,
    checkpoint_path: '',
    smart_router_enabled: false,
    smart_router_prefer_local: false,
    smart_router_budget_cap_usd: '',
    smart_router_latency_budget_ms: '',
    use_browser_vision: false
  };
  if (typeof localStorage === 'undefined') return writable(initial);
  const stored = localStorage.getItem(key);
  const value = stored ? { ...initial, ...JSON.parse(stored) } : initial;
  const store = writable<Settings>(value);
  store.subscribe((v) => localStorage.setItem(key, JSON.stringify(v)));
  return store;
}

export const settings = persistSettings();
