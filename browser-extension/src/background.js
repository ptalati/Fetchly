// Fetchly: hands browser downloads to the Fetchly app through the native messaging host.
// Works in Chrome, Edge, Brave (service worker) and Firefox (event page).
const api = typeof browser !== "undefined" ? browser : chrome;
const HOST = "app.fetchly.host";
const DEFAULTS = { enabled: true, minSizeMB: 0 };

// URLs we restarted in the browser after the host failed: never capture those again.
const passThrough = new Set();
// Downloads already being handled.
const handling = new Set();

function allowBrowserDownload(url) {
  passThrough.add(url);
  setTimeout(() => passThrough.delete(url), 60000);
}

function callHost(message) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (r) => { if (!done) { done = true; resolve(r); } };
    try {
      const result = api.runtime.sendNativeMessage(HOST, message, (reply) => {
        if (api.runtime.lastError) finish({ ok: false, error: api.runtime.lastError.message });
        else finish(reply || { ok: false, error: "no reply" });
      });
      // Firefox returns a promise instead of calling the callback.
      if (result && typeof result.then === "function") {
        result.then((r) => finish(r || { ok: false, error: "no reply" }),
                    (e) => finish({ ok: false, error: String((e && e.message) || e) }));
      }
    } catch (e) {
      finish({ ok: false, error: String((e && e.message) || e) });
    }
  });
}

async function settings() {
  const s = await api.storage.local.get(DEFAULTS);
  return { enabled: s.enabled !== false, minSizeMB: Number(s.minSizeMB) || 0 };
}

async function buildHeaders(url, referrer) {
  const headers = {};
  try {
    const cookies = await api.cookies.getAll({ url });
    if (cookies.length) headers["Cookie"] = cookies.map((c) => c.name + "=" + c.value).join("; ");
  } catch (e) { /* no cookie access: send without */ }
  if (referrer) headers["Referer"] = referrer;
  headers["User-Agent"] = navigator.userAgent;
  return headers;
}

async function capture(item) {
  const url = item.url || "";
  if (!/^https?:\/\//i.test(url)) return; // blob:, data:, file: stay in the browser
  if (handling.has(item.id) || passThrough.has(url)) return;
  const s = await settings();
  if (!s.enabled) return;
  if (s.minSizeMB > 0 && item.fileSize > 0 && item.fileSize < s.minSizeMB * 1024 * 1024) return;
  handling.add(item.id);
  try {
    try { await api.downloads.cancel(item.id); } catch (e) { /* already gone */ }
    try { await api.downloads.erase({ id: item.id }); } catch (e) { /* ignore */ }
    const filename = (item.filename || "").split(/[\\/]/).pop();
    const headers = await buildHeaders(url, item.referrer);
    const reply = await callHost({ type: "download", url, referrer: item.referrer || "", filename, headers });
    if (!reply.ok) {
      // Fetchly is not reachable: let the browser download it after all.
      allowBrowserDownload(url);
      try { await api.downloads.download({ url }); } catch (e) { /* nothing more to do */ }
    }
  } finally {
    handling.delete(item.id);
  }
}

api.downloads.onCreated.addListener((item) => { capture(item); });

api.runtime.onInstalled.addListener(() => {
  api.contextMenus.create(
    { id: "fetchly-link", title: "Download with Fetchly", contexts: ["link"] },
    () => void api.runtime.lastError,
  );
});

api.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "fetchly-link" || !info.linkUrl) return;
  if (!/^https?:\/\//i.test(info.linkUrl)) return;
  const referrer = info.pageUrl || (tab && tab.url) || "";
  const headers = await buildHeaders(info.linkUrl, referrer);
  const reply = await callHost({ type: "download", url: info.linkUrl, referrer, filename: "", headers });
  if (!reply.ok) {
    allowBrowserDownload(info.linkUrl);
    try { await api.downloads.download({ url: info.linkUrl }); } catch (e) { /* ignore */ }
  }
});

// The popup asks for the host status through the background script.
api.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "ping") {
    callHost({ type: "ping" }).then(sendResponse);
    return true;
  }
  return false;
});
