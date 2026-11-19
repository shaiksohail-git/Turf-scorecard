import { escapeHtml } from "../js/dom.js";

const STATUS_STYLES = {
  live: "bg-primary-400/15 text-primary-700 dark:text-primary-300",
  completed: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  draft: "bg-amber-400/15 text-amber-700 dark:text-amber-300",
  abandoned: "bg-red-400/15 text-red-700 dark:text-red-300",
};

const STATUS_LABELS = {
  live: "Live",
  completed: "Result",
  draft: "Draft",
  abandoned: "Abandoned",
};

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function statusBadge(status) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.completed;
  const label = STATUS_LABELS[status] || escapeHtml(status);
  return `<span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${style}">
    <span aria-hidden="true" class="h-1.5 w-1.5 rounded-full bg-current"></span>${escapeHtml(label)}
  </span>`;
}

export function teamName(match, teamId) {
  const team = (match.teams || []).find((item) => item.id === teamId);
  return team ? team.name : "Team";
}

export function inningsScore(innings) {
  if (!innings) return "—";
  return `${innings.runs}/${innings.wickets} (${innings.overs})`;
}

/** Two-line score block for a match card. */
export function scoreLines(match) {
  const rows = (match.innings || []).map((innings) => {
    const current = innings.status === "live";
    return `
      <div class="flex items-baseline justify-between gap-3">
        <span class="truncate text-sm ${current ? "font-semibold" : ""}">
          ${escapeHtml(teamName(match, innings.batting_team_id))}
        </span>
        <span class="shrink-0 text-sm tabular-nums ${current ? "font-semibold" : "text-zinc-600 dark:text-zinc-400"}">
          ${escapeHtml(inningsScore(innings))}
        </span>
      </div>`;
  });
  if (!rows.length) {
    return `<p class="text-sm text-zinc-500">Not started · ${match.overs} overs</p>`;
  }
  return `<div class="space-y-1.5">${rows.join("")}</div>`;
}

export function matchCard(match) {
  const href =
    match.status === "completed"
      ? `/pages/scorecard.html?match=${match.id}`
      : `/pages/live.html?match=${match.id}`;
  const meta = `${formatDate(match.date)}${match.venue ? ` · ${escapeHtml(match.venue)}` : ""} · ${match.overs} ov`;
  const result = match.result_summary
    ? `<p class="mt-3 text-sm font-medium text-primary-700 dark:text-primary-300">${escapeHtml(match.result_summary)}</p>`
    : "";

  return `
    <a href="${href}" class="block rounded-2xl border border-zinc-200 bg-white p-4 hover:border-primary-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-400 dark:border-zinc-800 dark:bg-zinc-900">
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs font-medium text-zinc-500 dark:text-zinc-400">${meta}</p>
        ${statusBadge(match.status)}
      </div>
      <div class="mt-3">${scoreLines(match)}</div>
      ${result}
    </a>`;
}

export function emptyState({ title, detail, href, label }) {
  const action =
    href && label
      ? `<a href="${href}" class="mt-4 inline-flex min-h-11 items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300">${escapeHtml(label)}</a>`
      : "";
  return `
    <div class="rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-6 text-center dark:border-zinc-700 dark:bg-zinc-900/40">
      <p class="text-sm font-semibold">${escapeHtml(title)}</p>
      <p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">${escapeHtml(detail)}</p>
      ${action}
    </div>`;
}

export function sectionHeader({ title, href, label }) {
  const action = href
    ? `<a href="${href}" class="text-sm font-semibold text-primary-700 hover:underline dark:text-primary-300">${escapeHtml(label || "View all")}</a>`
    : "";
  return `
    <div class="mb-3 flex items-baseline justify-between gap-3">
      <h2 class="text-base font-semibold tracking-tight">${escapeHtml(title)}</h2>
      ${action}
    </div>`;
}

export function errorPanel(message) {
  return `<p class="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-800 dark:text-red-200">${escapeHtml(message)}</p>`;
}
