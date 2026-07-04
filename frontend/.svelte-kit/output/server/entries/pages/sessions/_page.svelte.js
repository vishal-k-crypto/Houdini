import { a6 as head, aa as ensure_array_like, a7 as store_get, e as escape_html, a8 as attr_class, ab as stringify, ac as unsubscribe_stores } from "../../../chunks/index.js";
import { t as tasks } from "../../../chunks/store.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    function statusColor(status) {
      if (status === "completed") return "bg-green-900/40 text-green-400";
      if (status === "failed") return "bg-red-900/40 text-red-400";
      if (status === "running") return "bg-blue-900/40 text-blue-400";
      return "bg-orange-900/40 text-orange-400";
    }
    head("98wg7q", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>Houdini — Sessions</title>`);
      });
    });
    $$renderer2.push(`<div class="min-h-screen p-4 max-w-6xl mx-auto"><h1 class="text-xl font-bold text-blue-400 mb-4">Sessions</h1> <div class="bg-card border border-border rounded-lg p-4"><table class="w-full text-left"><thead class="text-xs uppercase text-gray-400"><tr><th class="pb-2">ID</th><th class="pb-2">Task</th><th class="pb-2">Architecture</th><th class="pb-2">Status</th><th class="pb-2">Duration</th><th class="pb-2">Actions</th></tr></thead><tbody class="text-sm">`);
    const each_array = ensure_array_like(store_get($$store_subs ??= {}, "$tasks", tasks));
    if (each_array.length !== 0) {
      $$renderer2.push("<!--[-->");
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let task = each_array[$$index];
        $$renderer2.push(`<tr class="border-t border-border hover:bg-[#0d1117]"><td class="py-2 font-mono text-xs text-gray-400">${escape_html(task.task_id)}</td><td class="py-2 max-w-xs truncate">${escape_html(task.task)}</td><td class="py-2 text-xs text-gray-400">${escape_html(task.architecture)}</td><td class="py-2"><span${attr_class(`text-[10px] px-2 py-0.5 rounded ${stringify(statusColor(task.status))}`)}>${escape_html(task.status)}</span></td><td class="py-2 text-xs text-gray-400">${escape_html(task.duration_s != null ? `${task.duration_s.toFixed(1)}s` : "—")}</td><td class="py-2"><a href="/" class="text-blue-400 hover:underline text-xs">View</a></td></tr>`);
      }
    } else {
      $$renderer2.push("<!--[!-->");
      $$renderer2.push(`<tr><td colspan="6" class="py-4 text-gray-500 italic text-sm">No sessions yet.</td></tr>`);
    }
    $$renderer2.push(`<!--]--></tbody></table></div></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
export {
  _page as default
};
