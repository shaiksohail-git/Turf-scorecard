/** Small DOM helpers shared by the page scripts. */

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => {
    switch (character) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      default:
        return "&#39;";
    }
  });
}

const MESSAGE_STYLES = {
  info: "border-zinc-300 bg-zinc-100 text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200",
  success:
    "border-primary-500/40 bg-primary-500/10 text-primary-800 dark:text-primary-200",
  error: "border-red-500/40 bg-red-500/10 text-red-800 dark:text-red-200",
};

/**
 * Render an accessible status/error/success box. Passing null clears it.
 */
export function setMessage(element, message) {
  if (!element) return;
  if (!message) {
    element.innerHTML = "";
    element.hidden = true;
    return;
  }
  const style = MESSAGE_STYLES[message.type] || MESSAGE_STYLES.info;
  const detail = message.detail
    ? `<p class="mt-1 text-sm opacity-90">${escapeHtml(message.detail)}</p>`
    : "";
  element.hidden = false;
  element.className = `rounded-xl border px-4 py-3 text-sm font-medium ${style}`;
  element.innerHTML = `<p>${escapeHtml(message.title)}</p>${detail}`;
}

export function describeDetails(details) {
  if (!details || typeof details !== "object") return "";
  const parts = [];
  if (Array.isArray(details.fields)) parts.push(`unknown: ${details.fields.join(", ")}`);
  if (Array.isArray(details.allowed)) parts.push(`allowed: ${details.allowed.join(", ")}`);
  if (typeof details.field === "string") parts.push(`field: ${details.field}`);
  if (details.expected !== undefined) parts.push(`expected: ${details.expected}`);
  if (details.received !== undefined) parts.push(`received: ${details.received}`);
  if (typeof details.reason === "string") parts.push(details.reason);
  return parts.join(" · ");
}
