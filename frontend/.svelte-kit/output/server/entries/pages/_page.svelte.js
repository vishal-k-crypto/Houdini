import { a5 as ssr_context, a6 as head, e as escape_html, a7 as store_get, a8 as attr_class, a9 as attr, aa as ensure_array_like, ab as stringify, ac as unsubscribe_stores } from "../../chunks/index.js";
import "clsx";
import { t as tasks, e as events, a as terminal, h as health, w as wsConnected, s as settings, b as selectedTaskId, c as screenshots, d as selectedTask } from "../../chunks/store.js";
function onDestroy(fn) {
  /** @type {SSRContext} */
  ssr_context.r.on_destroy(fn);
}
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    let taskInput = "";
    let busy = false;
    let polling;
    onDestroy(() => {
      window.clearInterval(polling);
    });
    function statusColor(status) {
      if (status === "completed") return "bg-green-900/40 text-green-400";
      if (status === "failed") return "bg-red-900/40 text-red-400";
      if (status === "running") return "bg-blue-900/40 text-blue-400";
      return "bg-orange-900/40 text-orange-400";
    }
    function truncate(s, n) {
      return s.length > n ? s.slice(0, n) + "…" : s;
    }
    head("1uha8ag", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>Houdini — Run</title>`);
      });
    });
    $$renderer2.push(`<div class="min-h-screen p-4"><header class="flex items-center justify-between mb-4"><h1 class="text-xl font-bold text-blue-400">Houdini Agent</h1> <div class="flex items-center gap-3"><span class="text-xs text-gray-400">Status: ${escape_html(store_get($$store_subs ??= {}, "$health", health)?.status || "—")}</span> <span class="flex items-center gap-1 text-xs"><span${attr_class(`w-2 h-2 rounded-full ${store_get($$store_subs ??= {}, "$wsConnected", wsConnected) ? "bg-green-400" : "bg-red-400"}`)}></span> ${escape_html(store_get($$store_subs ??= {}, "$wsConnected", wsConnected) ? "live" : "offline")}</span></div></header> <div class="grid grid-cols-12 gap-4"><div class="col-span-12 lg:col-span-4 space-y-4"><div class="bg-card border border-border rounded-lg p-4"><h2 class="text-xs uppercase text-gray-400 mb-2">New Task</h2> <textarea${attr("disabled", busy, true)} placeholder="Describe the task..." class="w-full h-24 bg-[#0d1117] border border-border rounded p-2 text-sm focus:border-blue-500 outline-none resize-none">`);
    const $$body = escape_html(taskInput);
    if ($$body) {
      $$renderer2.push(`${$$body}`);
    }
    $$renderer2.push(`</textarea> <div class="flex justify-between items-center mt-2"><span class="text-xs text-gray-500">Using ${escape_html(store_get($$store_subs ??= {}, "$settings", settings).provider || "ollama")} / ${escape_html(store_get($$store_subs ??= {}, "$settings", settings).model || "default")}</span> <button${attr("disabled", !taskInput.trim(), true)} class="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm font-semibold">${escape_html("Run")}</button></div> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="bg-card border border-border rounded-lg p-4"><h2 class="text-xs uppercase text-gray-400 mb-2">Sessions</h2> <div class="max-h-80 overflow-y-auto space-y-2">`);
    const each_array = ensure_array_like(store_get($$store_subs ??= {}, "$tasks", tasks));
    if (each_array.length !== 0) {
      $$renderer2.push("<!--[-->");
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let task = each_array[$$index];
        $$renderer2.push(`<button${attr_class("w-full text-left border border-border rounded p-2 hover:bg-[#0d1117] transition-colors", void 0, {
          "ring-2": store_get($$store_subs ??= {}, "$selectedTaskId", selectedTaskId) === task.task_id,
          "ring-blue-500": store_get($$store_subs ??= {}, "$selectedTaskId", selectedTaskId) === task.task_id
        })}><div class="flex justify-between items-center"><span class="text-xs font-mono text-gray-400">${escape_html(task.task_id)}</span> <span${attr_class(`text-[10px] px-2 py-0.5 rounded ${stringify(statusColor(task.status))}`)}>${escape_html(task.status)}</span></div> <p class="text-xs text-gray-300 mt-1 truncate">${escape_html(truncate(task.task, 60))}</p> <p class="text-[10px] text-gray-500 mt-1">${escape_html(task.architecture)}</p></button>`);
      }
    } else {
      $$renderer2.push("<!--[!-->");
      $$renderer2.push(`<p class="text-xs text-gray-500 italic">No sessions yet.</p>`);
    }
    $$renderer2.push(`<!--]--></div></div></div> <div class="col-span-12 lg:col-span-4 space-y-4"><div class="bg-card border border-border rounded-lg p-4"><h2 class="text-xs uppercase text-gray-400 mb-2">Live View</h2> `);
    if (store_get($$store_subs ??= {}, "$screenshots", screenshots).length > 0) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<img${attr("src", store_get($$store_subs ??= {}, "$screenshots", screenshots)[0].image_base64 || `data:image/png;base64,${store_get($$store_subs ??= {}, "$screenshots", screenshots)[0].image}`)} alt="latest screenshot" class="w-full rounded border border-border"/> <p class="text-[10px] text-gray-500 mt-1">${escape_html(store_get($$store_subs ??= {}, "$screenshots", screenshots)[0].timestamp)}</p>`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="w-full h-64 bg-[#0d1117] border border-dashed border-border rounded flex items-center justify-center text-xs text-gray-500">No live screenshot yet</div>`);
    }
    $$renderer2.push(`<!--]--></div> `);
    if (store_get($$store_subs ??= {}, "$selectedTask", selectedTask)) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="bg-card border border-border rounded-lg p-4"><h2 class="text-xs uppercase text-gray-400 mb-2">Selected Session</h2> <p class="text-xs font-mono text-gray-400 mb-1">${escape_html(store_get($$store_subs ??= {}, "$selectedTask", selectedTask).task_id)}</p> <p class="text-sm text-gray-200">${escape_html(store_get($$store_subs ??= {}, "$selectedTask", selectedTask).task)}</p> <p class="text-xs text-gray-500 mt-2">Architecture: ${escape_html(store_get($$store_subs ??= {}, "$selectedTask", selectedTask).architecture)}</p> <p class="text-xs text-gray-500">Status: ${escape_html(store_get($$store_subs ??= {}, "$selectedTask", selectedTask).status)}</p> `);
      if (store_get($$store_subs ??= {}, "$selectedTask", selectedTask).result) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<pre class="mt-2 text-[10px] bg-[#0d1117] border border-border rounded p-2 overflow-auto max-h-40">${escape_html(JSON.stringify(store_get($$store_subs ??= {}, "$selectedTask", selectedTask).result, null, 2))}</pre>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="col-span-12 lg:col-span-4 space-y-4"><div class="bg-card border border-border rounded-lg p-4"><h2 class="text-xs uppercase text-gray-400 mb-2">Thinking Log</h2> <div class="h-64 overflow-y-auto bg-[#0d1117] border border-border rounded p-2 text-[11px] space-y-1">`);
    const each_array_1 = ensure_array_like(store_get($$store_subs ??= {}, "$events", events));
    if (each_array_1.length !== 0) {
      $$renderer2.push("<!--[-->");
      for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
        let ev = each_array_1[$$index_1];
        $$renderer2.push(`<div class="border-b border-[#21262d] pb-1"><span class="text-gray-500 mr-1">${escape_html(ev.ts || "—")}</span> <span class="text-blue-300">${escape_html(ev.type)}</span> <span class="text-gray-300">${escape_html(truncate(JSON.stringify(ev), 120))}</span></div>`);
      }
    } else {
      $$renderer2.push("<!--[!-->");
      $$renderer2.push(`<p class="text-gray-500 italic">Waiting for events…</p>`);
    }
    $$renderer2.push(`<!--]--></div></div> <div class="bg-card border border-border rounded-lg p-4"><h2 class="text-xs uppercase text-gray-400 mb-2">Terminal</h2> <div class="h-64 overflow-y-auto bg-[#0d1117] border border-border rounded p-2 text-[11px] font-mono space-y-0.5">`);
    const each_array_2 = ensure_array_like(store_get($$store_subs ??= {}, "$terminal", terminal));
    if (each_array_2.length !== 0) {
      $$renderer2.push("<!--[-->");
      for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
        let line = each_array_2[$$index_2];
        $$renderer2.push(`<div><span class="text-gray-500 mr-2">${escape_html(line.ts)}</span> <span class="text-gray-300">${escape_html(line.text)}</span></div>`);
      }
    } else {
      $$renderer2.push("<!--[!-->");
      $$renderer2.push(`<p class="text-gray-500 italic">No terminal output.</p>`);
    }
    $$renderer2.push(`<!--]--></div></div></div></div></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
export {
  _page as default
};
