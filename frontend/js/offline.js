/** Durable local queue for scoring events.
 *
 * Every delivery is written to localStorage before it is sent. The server's
 * ``client_event_id`` unique constraint makes retries safe, so a sync can be
 * interrupted and resumed without double scoring. Undo and retirement actions
 * remain online-only because they need a coherent current innings state.
 *
 * Events rejected by the server are moved to a separate recovery list. Keeping
 * them at the head of the live queue would make every sync retry forever and
 * block all newer deliveries on the device.
 */
import { apiPost, ApiError } from "./api.js";

const QUEUE_KEY = "gully-score-queue-v1";
const FAILED_KEY = "gully-score-failed-v1";
const SYNC_TAG = "gully-score-sync";
let syncing = null;

function readQueue() {
  try {
    const parsed = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeQueue(queue) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  } catch {
    /* private mode: the server request can still be attempted */
  }
  window.dispatchEvent(new CustomEvent("gully:queue", { detail: { count: queue.length } }));
}

function readFailed() {
  try {
    const parsed = JSON.parse(localStorage.getItem(FAILED_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeFailed(entries) {
  try {
    localStorage.setItem(FAILED_KEY, JSON.stringify(entries));
  } catch {
    /* private mode: the live queue still works */
  }
}

function archiveRejected(item, error) {
  const entries = readFailed();
  const eventId = item?.payload?.client_event_id;
  if (eventId && entries.some((entry) => entry.item?.payload?.client_event_id === eventId)) return;
  entries.push({
    item,
    message: error?.message || "The server rejected this delivery.",
    status: error?.status || null,
    rejectedAt: new Date().toISOString(),
  });
  writeFailed(entries);
}

function removeFirst() {
  const queue = readQueue();
  queue.shift();
  writeQueue(queue);
}

export function pendingDeliveries() {
  return readQueue().length;
}

export function failedDeliveries() {
  return readFailed();
}

export function clearFailedDeliveries() {
  writeFailed([]);
  window.dispatchEvent(new CustomEvent("gully:queue"));
}

export function enqueueDelivery(inningsId, payload) {
  const queue = readQueue();
  const eventId = payload.client_event_id;
  if (!queue.some((item) => item.inningsId === inningsId && item.payload.client_event_id === eventId)) {
    queue.push({
      inningsId,
      payload,
      queuedAt: new Date().toISOString(),
    });
    writeQueue(queue);
  }
  if ("serviceWorker" in navigator && "SyncManager" in window) {
    navigator.serviceWorker.ready
      .then((registration) => registration.sync?.register(SYNC_TAG))
      .catch(() => {});
  }
  return pendingDeliveries();
}

export async function flushDeliveryQueue({ onConflict, onError } = {}) {
  if (syncing) return syncing;
  if (!navigator.onLine || !readQueue().length) return { sent: 0, pending: pendingDeliveries() };

  syncing = (async () => {
    let sent = 0;
    while (readQueue().length) {
      const item = readQueue()[0];
      try {
        await apiPost(`/api/innings/${item.inningsId}/deliveries`, item.payload);
        removeFirst();
        sent += 1;
      } catch (error) {
        if (error instanceof ApiError && [409, 422].includes(error.status)) {
          // A rejected event must not poison the queue. Preserve it locally so
          // the scorer can inspect/discard it, and let later balls sync.
          archiveRejected(item, error);
          removeFirst();
          onConflict?.(error, item);
          break;
        }
        if (error instanceof ApiError && error.status === 401) break;
        // Network or server failure: keep the event for the next connection.
        onError?.(error, item);
        break;
      }
    }
    return { sent, pending: pendingDeliveries(), failed: readFailed().length };
  })().finally(() => {
    syncing = null;
  });
  return syncing;
}

export function subscribeQueue(callback) {
  const handler = (event) => callback(event.detail?.count ?? pendingDeliveries());
  window.addEventListener("gully:queue", handler);
  return () => window.removeEventListener("gully:queue", handler);
}
