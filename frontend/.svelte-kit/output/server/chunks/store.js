import { d as derived, w as writable } from "./index2.js";
const tasks = writable([]);
const health = writable(null);
const wsConnected = writable(false);
const terminal = writable([]);
const screenshots = writable([]);
const events = writable([]);
const selectedTaskId = writable(null);
const selectedTask = derived(
  [tasks, selectedTaskId],
  ([$tasks, $id]) => $tasks.find((t) => t.task_id === $id) || null
);
function persistSettings() {
  const key = "houdini.settings";
  const initial = {
    provider: "ollama",
    model: "qwen3-coder:480b-cloud",
    api_key: "",
    api_base: "",
    architecture: "adaptive",
    use_enhanced: true,
    thinking_window: false,
    checkpoint_path: ""
  };
  if (typeof localStorage === "undefined") return writable(initial);
  const stored = localStorage.getItem(key);
  const value = stored ? { ...initial, ...JSON.parse(stored) } : initial;
  const store = writable(value);
  store.subscribe((v) => localStorage.setItem(key, JSON.stringify(v)));
  return store;
}
const settings = persistSettings();
export {
  terminal as a,
  selectedTaskId as b,
  screenshots as c,
  selectedTask as d,
  events as e,
  health as h,
  settings as s,
  tasks as t,
  wsConnected as w
};
