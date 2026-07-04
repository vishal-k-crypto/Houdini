import { a6 as head } from "../../../chunks/index.js";
import "../../../chunks/store.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    head("1i19ct2", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>Houdini — Settings</title>`);
      });
    });
    $$renderer2.push(`<div class="min-h-screen p-4 max-w-4xl mx-auto"><h1 class="text-xl font-bold text-blue-400 mb-4">Settings</h1> <div class="bg-card border border-border rounded-lg p-6 space-y-4">`);
    {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<p class="text-sm text-gray-400">Loading providers…</p>`);
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> <div class="flex items-center gap-3"><button class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-semibold">Save Settings</button> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div></div></div>`);
  });
}
export {
  _page as default
};
