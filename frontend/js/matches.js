import { apiGet, apiGetPage } from "./api.js";
import { escapeHtml } from "./dom.js";
import { renderShell } from "../components/shell.js";
import { emptyState, errorPanel, matchCard } from "../components/ui.js";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "live", label: "Live" },
  { key: "completed", label: "Completed" },
  { key: "draft", label: "Drafts" },
];

const params = new URLSearchParams(window.location.search);
const seriesId = Number(params.get("series")) || null;
let activeFilter = params.get("status") || "all";
let series = null;
let page = 1;
let hasMore = true;
let loading = false;

function renderFilters() {
  const container = document.getElementById("match-filters");
  if (!container) return;
  container.innerHTML = FILTERS.map((filter) => {
    const active = filter.key === activeFilter;
    const classes = active
      ? "bg-primary-400 text-emerald-950"
      : "border border-zinc-300 text-zinc-700 hover:border-primary-400 dark:border-zinc-700 dark:text-zinc-300";
    return `<button type="button" data-status="${filter.key}" aria-pressed="${active}"
      class="min-h-11 rounded-full px-4 text-sm font-semibold ${classes}">${filter.label}</button>`;
  }).join("");

  container.querySelectorAll("[data-status]").forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.status;
      const next = new URLSearchParams(window.location.search);
      if (activeFilter === "all") next.delete("status");
      else next.set("status", activeFilter);
      window.history.replaceState({}, "", `${window.location.pathname}?${next.toString()}`);
      renderFilters();
      load({ reset: true });
    });
  });
}

async function loadSeries() {
  if (!seriesId) return;
  try {
    series = await apiGet(`/api/series/${seriesId}`);
    const subtitle = document.getElementById("matches-subtitle");
    if (subtitle) {
      subtitle.innerHTML = `<a href="/pages/series.html?id=${series.id}" class="font-semibold text-primary-700 hover:underline dark:text-primary-300">${escapeHtml(series.name)}</a> · ${series.match_count} match${series.match_count === 1 ? "" : "es"} · <a href="/pages/series.html?id=${series.id}" class="underline">Series dashboard</a>`;
    }
  } catch {
    /* the list below still renders */
  }
}

function loadMoreControl() {
  const wrap = document.getElementById("load-more-wrap");
  const button = document.getElementById("load-more");
  const note = document.getElementById("load-more-note");
  if (!wrap || !button || !note) return;
  wrap.hidden = !hasMore;
  button.disabled = loading;
  button.textContent = loading ? "Loading…" : "Load more";
  note.textContent = hasMore ? "Newest matches are shown first." : "";
}

async function load({ reset = false } = {}) {
  const list = document.getElementById("matches-list");
  if (!list || loading) return;
  if (reset) {
    page = 1;
    hasMore = true;
    list.innerHTML = "";
  }
  loading = true;
  list.setAttribute("aria-busy", "true");
  loadMoreControl();
  const query = new URLSearchParams({ page: String(page), per_page: "20" });
  if (activeFilter !== "all") query.set("status", activeFilter);
  if (seriesId) query.set("series_id", String(seriesId));

  try {
    const payload = await apiGetPage(`/api/matches?${query.toString()}`);
    const matches = Array.isArray(payload.data) ? payload.data : [];
    const meta = payload.meta || {};
    hasMore = Boolean(meta.has_more ?? matches.length === 20);
    if (matches.length) {
      list.insertAdjacentHTML("beforeend", matches.map(matchCard).join(""));
    } else if (page === 1) {
      list.innerHTML = emptyState({
        title: "Nothing here yet",
        detail:
          activeFilter === "live"
            ? "No match is currently in progress."
            : "Create a match and it will show up in your history.",
        href: "/pages/match-type.html",
        label: "New match",
      });
    }
    page += 1;
  } catch (error) {
    list.insertAdjacentHTML("beforeend", errorPanel(error.message));
    hasMore = false;
  } finally {
    loading = false;
    list.setAttribute("aria-busy", "false");
    loadMoreControl();
  }
}

async function init() {
  renderShell("matches");
  renderFilters();
  document.getElementById("load-more")?.addEventListener("click", () => load());
  await loadSeries();
  await load({ reset: true });
}

init();
