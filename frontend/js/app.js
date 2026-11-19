import { fetchHealth, fetchPresets } from "./api.js";
import { escapeHtml } from "./dom.js";
import { renderNav } from "../components/nav.js";
import { renderFooter } from "../components/footer.js";

function presetCard(preset) {
  const rules = preset.rules;
  const chips = [
    `${rules.overs} overs`,
    `${rules.players_per_team} a side`,
    `${rules.balls_per_over} balls/over`,
    rules.free_hit_enabled ? "Free hit" : "No free hit",
    rules.solo_batting_enabled ? "Solo batting" : "Standard batting",
  ];

  return `
    <article class="flex h-full flex-col rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <h3 class="text-base font-semibold">${escapeHtml(preset.label)}</h3>
      <p class="mt-2 text-sm text-zinc-600 dark:text-zinc-400">${escapeHtml(preset.description)}</p>
      <ul class="mt-4 flex flex-wrap gap-2">
        ${chips
          .map(
            (chip) =>
              `<li class="rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">${escapeHtml(chip)}</li>`,
          )
          .join("")}
      </ul>
      <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt class="text-xs text-zinc-500">Wide penalty</dt>
          <dd class="font-semibold">${rules.wide_penalty}</dd>
        </div>
        <div>
          <dt class="text-xs text-zinc-500">No-ball penalty</dt>
          <dd class="font-semibold">${rules.no_ball_penalty}</dd>
        </div>
        <div>
          <dt class="text-xs text-zinc-500">Innings balls</dt>
          <dd class="font-semibold">${rules.total_balls}</dd>
        </div>
        <div>
          <dt class="text-xs text-zinc-500">Wickets to end</dt>
          <dd class="font-semibold">${rules.max_wickets}</dd>
        </div>
      </dl>
      <a
        href="/pages/rules.html?preset=${encodeURIComponent(preset.key)}"
        class="mt-5 inline-flex min-h-11 items-center justify-center rounded-xl border border-zinc-300 px-4 text-sm font-semibold text-zinc-800 hover:border-primary-500 hover:text-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500 dark:border-zinc-700 dark:text-zinc-100 dark:hover:text-primary-300"
        >Review settings</a
      >
    </article>`;
}

async function loadPresets() {
  const container = document.getElementById("presets");
  if (!container) return;
  try {
    const data = await fetchPresets();
    container.innerHTML = data.presets.map(presetCard).join("");
    container.setAttribute("aria-busy", "false");
  } catch (error) {
    container.innerHTML = `
      <p class="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-800 dark:text-red-200">
        ${escapeHtml(error.message)}
      </p>`;
    container.setAttribute("aria-busy", "false");
  }
}

async function checkHealth() {
  const line = document.getElementById("status-line");
  if (!line) return;
  line.textContent = "Checking the API…";
  try {
    const health = await fetchHealth();
    line.innerHTML = `
      <span class="font-semibold text-primary-700 dark:text-primary-300">API online</span>
      <span aria-hidden="true"> · </span>
      v${escapeHtml(health.version)}
      <span aria-hidden="true"> · </span>
      database ${health.database ? "connected" : "unavailable"}`;
  } catch (error) {
    line.innerHTML = `<span class="font-semibold text-red-700 dark:text-red-300">API offline</span><span aria-hidden="true"> · </span>${escapeHtml(error.message)}`;
  }
}

function init() {
  renderNav("home");
  renderFooter();
  loadPresets();
  checkHealth();

  const refresh = document.getElementById("refresh-health");
  if (refresh) refresh.addEventListener("click", checkHealth);
}

init();
