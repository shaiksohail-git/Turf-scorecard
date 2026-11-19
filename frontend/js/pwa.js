/** PWA registration and the shared online/offline indicator. */

let started = false;
let updateReady = false;

function ensureIndicator() {
  if (document.getElementById("gully-connectivity")) return;
  const node = document.createElement("div");
  node.id = "gully-connectivity";
  node.setAttribute("role", "status");
  node.setAttribute("aria-live", "polite");
  node.className =
    "fixed inset-x-4 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-40 hidden rounded-xl border px-3 py-2 text-center text-xs font-semibold shadow-lg lg:bottom-4";
  document.body.appendChild(node);
}

function renderConnectivity() {
  ensureIndicator();
  const node = document.getElementById("gully-connectivity");
  if (!node) return;
  const online = navigator.onLine;
  node.hidden = online;
  node.textContent = online
    ? ""
    : "Offline mode · scores are saved on this device and will sync when connected";
  node.className = online
    ? "hidden"
    : "fixed inset-x-4 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-40 rounded-xl border border-amber-400/50 bg-amber-400/95 px-3 py-2 text-center text-xs font-semibold text-amber-950 shadow-lg lg:bottom-4";
  document.documentElement.dataset.online = String(online);
}

export function registerPwa() {
  if (started) return;
  started = true;
  ensureIndicator();
  renderConnectivity();

  window.addEventListener("online", () => {
    renderConnectivity();
    window.dispatchEvent(new CustomEvent("gully:online"));
  });
  window.addEventListener("offline", () => {
    renderConnectivity();
    window.dispatchEvent(new CustomEvent("gully:offline"));
  });

  navigator.serviceWorker?.addEventListener("message", (event) => {
    if (event.data?.type === "GULLY_SYNC_REQUEST") {
      window.dispatchEvent(new CustomEvent("gully:sync"));
    }
  });

  // Reload once when a new worker takes control so the page is never stuck on
  // an old cached shell after a deploy.
  navigator.serviceWorker?.addEventListener("controllerchange", () => {
    if (!updateReady) return;
    updateReady = false;
    window.location.reload();
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then((registration) => {
        registration.addEventListener("updatefound", () => {
          const worker = registration.installing;
          worker?.addEventListener("statechange", () => {
            if (worker.state === "installed" && navigator.serviceWorker.controller) {
              updateReady = true;
              worker.postMessage({ type: "SKIP_WAITING" });
            }
          });
        });
      })
      .catch(() => {
        /* A service worker is an enhancement; the app remains usable without it. */
      });
  }
}

export function isOnline() {
  return navigator.onLine;
}
