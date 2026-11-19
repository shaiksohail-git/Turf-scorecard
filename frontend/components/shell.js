import { initThemeToggle } from "../js/theme.js";
import { escapeHtml } from "../js/dom.js";
import { registerPwa } from "../js/pwa.js";

const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
  matches:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h10M7 17h6"/>',
  stats: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  settings:
    '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 8.9 19a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 5 8.9a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};

const NAV = [
  { key: "home", label: "Home", href: "/" },
  { key: "matches", label: "Matches", href: "/pages/matches.html" },
  { key: "stats", label: "Stats", href: "/pages/stats.html" },
  { key: "settings", label: "Settings", href: "/pages/settings.html" },
];

const THEME_ICON = (classes) => `
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" class="${classes} dark:hidden" aria-hidden="true">
    <circle cx="12" cy="12" r="4"></circle>
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>
  </svg>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" class="hidden ${classes} dark:block" aria-hidden="true">
    <path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8Z"></path>
  </svg>`;

function icon(name, classes = "h-5 w-5") {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" class="${classes}" aria-hidden="true">${ICONS[name]}</svg>`;
}

function brand() {
  return `
    <a href="/" class="flex items-center gap-2.5 rounded-lg px-1 py-1 text-base font-semibold tracking-tight">
      <span aria-hidden="true" class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary-400 text-sm font-bold text-emerald-950">GS</span>
      <span>GullyScore</span>
    </a>`;
}

function sidebar(active) {
  const items = NAV.map((item) => {
    const isActive = item.key === active;
    const classes = isActive
      ? "bg-primary-400/15 text-primary-700 dark:text-primary-300"
      : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-100";
    return `
      <a href="${item.href}" class="flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-semibold ${classes}"
        ${isActive ? 'aria-current="page"' : ""}>
        ${icon(item.key)}
        <span>${escapeHtml(item.label)}</span>
      </a>`;
  }).join("");

  return `
    <aside id="app-sidebar" aria-label="Primary navigation" class="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-zinc-200 bg-white px-4 py-5 dark:border-zinc-800 dark:bg-zinc-950 lg:flex">
      <button id="sidebar-close" type="button" aria-label="Hide navigation" class="absolute right-3 top-3 inline-flex h-9 w-9 items-center justify-center rounded-lg text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-100">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" class="h-5 w-5" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
      ${brand()}
      <nav aria-label="Primary" class="mt-8 flex flex-1 flex-col gap-1.5">${items}</nav>
      <div class="mt-6 space-y-3">
        <a href="/pages/match-type.html" class="flex min-h-12 items-center justify-center gap-2 rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-400">
          ${icon("plus", "h-4 w-4")}
          New match
        </a>
        <button type="button" data-theme-toggle aria-pressed="true" class="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-zinc-300 px-4 text-sm font-semibold text-zinc-700 hover:border-primary-400 hover:text-primary-700 dark:border-zinc-700 dark:text-zinc-300 dark:hover:text-primary-300">
          ${THEME_ICON("h-5 w-5")}
          <span class="sr-only">Toggle colour theme</span>
        </button>
        <p class="px-1 text-xs text-zinc-500 dark:text-zinc-500">Phase 5 · Tested, offline-ready</p>
      </div>
    </aside>`;
}

function topbar() {
  return `
    <header class="sticky top-0 z-20 flex items-center justify-between gap-2 border-b border-zinc-200 bg-white/95 px-4 py-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/95 lg:hidden">
      ${brand()}
      <button type="button" data-theme-toggle aria-pressed="true" class="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-zinc-300 text-zinc-700 dark:border-zinc-700 dark:text-zinc-300">
        ${THEME_ICON("h-5 w-5")}
        <span class="sr-only">Toggle colour theme</span>
      </button>
    </header>`;
}

function bottomNav(active) {
  const items = NAV.map((item) => {
    const isActive = item.key === active;
    const classes = isActive
      ? "text-primary-700 dark:text-primary-300"
      : "text-zinc-500 dark:text-zinc-400";
    return `
      <a href="${item.href}" class="flex min-h-16 flex-col items-center justify-center gap-1 text-[11px] font-semibold ${classes}"
        ${isActive ? 'aria-current="page"' : ""}>
        ${icon(item.key, "h-5 w-5")}
        <span>${escapeHtml(item.label)}</span>
      </a>`;
  }).join("");

  return `
    <nav class="safe-bottom fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950 lg:hidden" aria-label="Primary">
      ${items}
    </nav>`;
}

/**
 * Render the shared app shell (sidebar on desktop, top bar + bottom nav on
 * mobile) into #shell and prepare the main element.
 * @param {"home"|"matches"|"stats"|"settings"|""} active
 */
export function renderShell(active = "") {
  const root = document.getElementById("shell");
  if (!root) return;
  root.innerHTML = `
    ${sidebar(active)}
    <button id="sidebar-open" type="button" aria-label="Show navigation" aria-controls="app-sidebar" aria-expanded="false" class="fixed left-4 top-4 z-40 hidden h-11 w-11 items-center justify-center rounded-xl border border-zinc-300 bg-white text-zinc-700 shadow-sm hover:border-primary-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" class="h-5 w-5" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
    </button>
    ${topbar()}
    ${bottomNav(active)}`;

  const main = document.getElementById("main");
  if (main) {
    main.classList.add(
      "mx-auto",
      "w-full",
      "max-w-5xl",
      "px-4",
      "pb-28",
      "pt-6",
      "sm:px-6",
      "lg:pb-12",
    );
  }

  initThemeToggle();
  initSidebar();
  registerPwa();
}

/** Keep the desktop sidebar from covering the content, and let it collapse. */
function initSidebar() {
  const aside = document.getElementById("app-sidebar");
  const close = document.getElementById("sidebar-close");
  const open = document.getElementById("sidebar-open");
  if (!aside || !close || !open) return;

  const desktop = window.matchMedia("(min-width: 1024px)");
  let expanded = true;
  try {
    expanded = localStorage.getItem("gully-sidebar") !== "closed";
  } catch {
    /* private mode: default open */
  }

  function apply(next = expanded) {
    expanded = next;
    if (!desktop.matches) {
      aside.classList.add("hidden");
      aside.style.display = "";
      document.body.classList.remove("lg:pl-72");
      open.classList.add("hidden");
      return;
    }
    aside.classList.remove("hidden");
    aside.style.display = expanded ? "" : "none";
    document.body.classList.toggle("lg:pl-72", expanded);
    open.classList.toggle("hidden", expanded);
    open.setAttribute("aria-expanded", String(!expanded));
  }

  function remember(next) {
    try {
      localStorage.setItem("gully-sidebar", next ? "open" : "closed");
    } catch {
      /* the toggle still works for this page load */
    }
  }

  close.addEventListener("click", () => {
    remember(false);
    apply(false);
    open.focus();
  });
  open.addEventListener("click", () => {
    remember(true);
    apply(true);
    close.focus();
  });
  desktop.addEventListener("change", () => apply(expanded));
  apply(expanded);
}
