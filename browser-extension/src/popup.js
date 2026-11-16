const api = typeof browser !== "undefined" ? browser : chrome;
const enabled = document.getElementById("enabled");
const minSize = document.getElementById("minSize");
const status = document.getElementById("status");

api.storage.local.get({ enabled: true, minSizeMB: 0 }).then((s) => {
  enabled.checked = s.enabled !== false;
  minSize.value = Number(s.minSizeMB) || 0;
});
enabled.addEventListener("change", () => api.storage.local.set({ enabled: enabled.checked }));
minSize.addEventListener("change", () => {
  const v = Math.max(0, Number(minSize.value) || 0);
  minSize.value = v;
  api.storage.local.set({ minSizeMB: v });
});

function show(ok, text) {
  status.textContent = text;
  status.className = ok ? "ok" : "bad";
}
const NOT_FOUND = "Fetchly not found - install or start the app";
api.runtime.sendMessage({ type: "ping" }).then(
  (reply) => (reply && reply.ok ? show(true, "Fetchly connected") : show(false, NOT_FOUND)),
  () => show(false, NOT_FOUND),
);
