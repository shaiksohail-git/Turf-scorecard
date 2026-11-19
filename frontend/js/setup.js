import { apiGet, apiPost, fetchPresets } from "./api.js";
import { describeDetails, escapeHtml, setMessage } from "./dom.js";
import { renderShell } from "../components/shell.js";

const PRESET_KEY = document.body.dataset.preset || "custom_turf";
const SERIES_ID = Number(new URLSearchParams(window.location.search).get("series")) || null;
const root = document.getElementById("setup-root");
let selectedSeries = null;

const RETIREMENT_LABELS = {
  retired_not_out: "Retired – Not Out",
  retired_out: "Retired – Out",
  retired_hurt: "Retired – Hurt",
};

const NUMBER_FIELDS = [
  ["overs", "Overs per innings", 1, 50],
  ["balls_per_over", "Balls per over", 1, 12],
  ["players_per_team", "Players per team", 2, 11],
  ["wide_penalty", "Wide penalty", 0, 5],
  ["no_ball_penalty", "No-ball penalty", 0, 5],
];

const FLAG_FIELDS = [
  ["wide_counts_as_legal_ball", "Wide counts as a legal ball"],
  ["no_ball_counts_as_legal_ball", "No-ball counts as a legal ball"],
  ["free_hit_enabled", "Free hit after a no-ball"],
  ["solo_batting_enabled", "Solo batting (last batter continues alone)"],
  ["retired_player_option", "Allow retired players"],
];

const inputClasses =
  "mt-2 min-h-12 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm text-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100";
const checkClasses =
  "h-5 w-5 shrink-0 rounded border-zinc-400 text-primary-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-400";
const cardClasses =
  "rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900";
const labelClasses = "block text-sm font-medium";

let submitting = false;
let createdMatchId = null;

function numberField([name, label, min, max], value) {
  return `
    <div>
      <label for="${name}" class="${labelClasses}">${label}</label>
      <input id="${name}" name="${name}" type="number" inputmode="numeric" min="${min}" max="${max}"
        value="${escapeHtml(value)}" required class="${inputClasses}" />
    </div>`;
}

function flagField([name, label], checked) {
  return `
    <label class="flex min-h-11 items-center gap-3 text-sm">
      <input id="${name}" type="checkbox" class="${checkClasses}" ${checked ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>`;
}

function formHtml(preset, series) {
  const rules = preset.rules;
  const teamA = series?.team_a || { name: "", players: [] };
  const teamB = series?.team_b || { name: "", players: [] };

  return `
    <header>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <a href="/pages/match-type.html${SERIES_ID ? `?series=${SERIES_ID}` : ""}" class="text-sm font-semibold text-zinc-500 hover:text-primary-700 dark:text-zinc-400 dark:hover:text-primary-300">← Match types</a>
        ${series ? `<a href="/pages/series.html?id=${series.id}" class="text-sm font-semibold text-primary-700 hover:underline dark:text-primary-300">Series: ${escapeHtml(series.name)}</a>` : ""}
      </div>
      <h1 class="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">${escapeHtml(preset.label)} setup</h1>
      <p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">${escapeHtml(preset.description)} The rules you save become this match's snapshot.</p>
      ${series ? `<p class="mt-2 rounded-xl border border-primary-500/30 bg-primary-500/10 px-3 py-2 text-sm text-primary-800 dark:text-primary-200">This match will be added to <strong>${escapeHtml(series.name)}</strong>. The series roster and planned length do not change until you edit the series.</p>` : ""}
    </header>

    <form id="setup-form" class="mt-6 space-y-5" novalidate>
      <section class="${cardClasses}">
        <h2 class="text-base font-semibold">Match details</h2>
        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <label for="venue" class="${labelClasses}">Venue <span class="text-xs text-zinc-500">(optional)</span></label>
            <input id="venue" name="venue" type="text" maxlength="120" placeholder="Local turf" class="${inputClasses}" />
          </div>
          <div>
            <label for="toss_winner" class="${labelClasses}">Toss winner</label>
            <select id="toss_winner" class="${inputClasses}">
              <option value="a">Team A</option>
              <option value="b">Team B</option>
            </select>
          </div>
          <div>
            <label for="toss_decision" class="${labelClasses}">Toss decision</label>
            <select id="toss_decision" class="${inputClasses}">
              <option value="bat">Bat first</option>
              <option value="bowl">Bowl first</option>
            </select>
          </div>
        </div>
      </section>

      <section class="${cardClasses}">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="text-base font-semibold">Teams and squads</h2>
          <p class="text-xs text-zinc-500 dark:text-zinc-400">Squad order is the batting order.</p>
        </div>
        <div class="mt-4 grid gap-5 sm:grid-cols-2">
          ${["a", "b"]
            .map(
              (side) => `
            <fieldset>
              <legend class="text-sm font-semibold">Team ${side.toUpperCase()}</legend>
              <label for="team_${side}_name" class="${labelClasses} mt-2">Team name</label>
              <input id="team_${side}_name" type="text" maxlength="80" required
                value="${escapeHtml((side === "a" ? teamA : teamB).name || "")}"
                placeholder="${side === "a" ? "Green Caps" : "Night Riders"}" class="${inputClasses}" />
              <label for="team_${side}_players" class="${labelClasses} mt-4">Squad</label>
              <textarea id="team_${side}_players" data-squad rows="${Math.max(4, Math.min(14, rules.players_per_team))}"
                class="${inputClasses} py-2 font-mono text-xs leading-6" spellcheck="false"
                placeholder="One player per line">${escapeHtml(((side === "a" ? teamA : teamB).players || []).join("\n"))}</textarea>
              <p data-squad-hint class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">One player per line — exactly ${rules.players_per_team} required</p>
            </fieldset>`,
            )
            .join("")}
        </div>
      </section>

      <section class="${cardClasses}">
        <h2 class="text-base font-semibold">Rules</h2>
        <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Defaults come from ${escapeHtml(preset.label)}. Changes apply to this match only.</p>
        <div class="mt-4 grid gap-4 sm:grid-cols-3">
          ${NUMBER_FIELDS.map((field) => numberField(field, rules[field[0]])).join("")}
          <div>
            <label for="max_overs_per_bowler" class="${labelClasses}">Max overs per bowler</label>
            <input id="max_overs_per_bowler" type="number" inputmode="numeric" min="1" max="50"
              value="${rules.max_overs_per_bowler ?? ""}" placeholder="No limit" class="${inputClasses}" />
          </div>
        </div>

        <div class="mt-4 grid gap-2 sm:grid-cols-2">
          ${FLAG_FIELDS.map(([name, label]) => flagField([name, label], rules[name])).join("")}
        </div>

        <div class="mt-5">
          <p class="text-sm font-medium">Runs allowed off the bat</p>
          <div class="mt-2 flex flex-wrap gap-2">
            ${[0, 1, 2, 3, 4, 5, 6]
              .map(
                (run) => `
              <label class="inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center gap-2 rounded-xl border border-zinc-300 px-3 text-sm font-medium dark:border-zinc-700">
                <input type="checkbox" name="allowed_runs" value="${run}" class="${checkClasses}"
                  ${rules.allowed_runs.includes(run) ? "checked" : ""} />
                <span>${run}</span>
              </label>`,
              )
              .join("")}
          </div>
        </div>

        <div class="mt-5">
          <p class="text-sm font-medium">Retirement types</p>
          <div class="mt-2 grid gap-2 sm:grid-cols-3">
            ${rules.retirement_types
              .map(
                (kind) => `
              <label class="flex min-h-11 items-center gap-2 rounded-xl border border-zinc-300 px-3 text-sm dark:border-zinc-700">
                <input type="checkbox" name="retirement_types" value="${escapeHtml(kind)}" class="${checkClasses}" checked />
                <span>${escapeHtml(RETIREMENT_LABELS[kind] || kind)}</span>
              </label>`,
              )
              .join("")}
          </div>
        </div>
      </section>

      <div id="setup-feedback" hidden></div>

      <div class="flex flex-wrap gap-3">
        <button id="setup-submit" type="submit"
          class="inline-flex min-h-12 items-center justify-center rounded-xl bg-primary-400 px-5 text-sm font-bold text-emerald-950 hover:bg-primary-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-400">
          Create match &amp; start scoring
        </button>
        <a href="/pages/match-type.html"
          class="inline-flex min-h-12 items-center justify-center rounded-xl border border-zinc-300 px-5 text-sm font-semibold text-zinc-800 dark:border-zinc-700 dark:text-zinc-100">
          Cancel
        </a>
      </div>
    </form>`;
}

function value(id) {
  return document.getElementById(id)?.value.trim() ?? "";
}

function numberValue(id) {
  return Number(document.getElementById(id)?.value);
}

function checked(id) {
  return Boolean(document.getElementById(id)?.checked);
}

function checkedValues(name) {
  return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(
    (input) => input.value,
  );
}

function collectRules() {
  return {
    overs: numberValue("overs"),
    balls_per_over: numberValue("balls_per_over"),
    players_per_team: numberValue("players_per_team"),
    wide_penalty: numberValue("wide_penalty"),
    wide_counts_as_legal_ball: checked("wide_counts_as_legal_ball"),
    no_ball_penalty: numberValue("no_ball_penalty"),
    no_ball_counts_as_legal_ball: checked("no_ball_counts_as_legal_ball"),
    free_hit_enabled: checked("free_hit_enabled"),
    solo_batting_enabled: checked("solo_batting_enabled"),
    allowed_runs: checkedValues("allowed_runs").map(Number),
    retired_player_option: checked("retired_player_option"),
    retirement_types: checkedValues("retirement_types"),
    max_overs_per_bowler:
      value("max_overs_per_bowler") === "" ? null : numberValue("max_overs_per_bowler"),
  };
}

function squad(id) {
  return value(id)
    .split(/\r?\n/)
    .map((name) => name.trim())
    .filter(Boolean);
}

function feedback(message) {
  const element = document.getElementById("setup-feedback");
  setMessage(element, message);
  if (message) element.scrollIntoView({ block: "nearest" });
}

function setBusy(busy) {
  submitting = busy;
  const button = document.getElementById("setup-submit");
  if (!button) return;
  button.disabled = busy;
  if (busy) {
    button.setAttribute("aria-busy", "true");
    button.textContent = "Creating match…";
  } else {
    button.removeAttribute("aria-busy");
    button.textContent = "Create match & start scoring";
  }
}

function syncSquadHints() {
  const count = numberValue("players_per_team") || 0;
  document.querySelectorAll("[data-squad-hint]").forEach((element) => {
    element.textContent = `One player per line — exactly ${count} required`;
  });
  document.querySelectorAll("[data-squad]").forEach((element) => {
    element.rows = Math.max(4, Math.min(14, count));
  });
}

function validate(payload) {
  const expected = payload.rules.players_per_team;
  if (!payload.team_a.name || !payload.team_b.name) {
    return "Both team names are required.";
  }
  if (payload.team_a.name.toLowerCase() === payload.team_b.name.toLowerCase()) {
    return "The two teams must have different names.";
  }
  for (const [key, team] of [
    ["A", payload.team_a],
    ["B", payload.team_b],
  ]) {
    if (team.players.length !== expected) {
      return `Team ${key} needs exactly ${expected} players — ${team.players.length} found.`;
    }
    const lower = team.players.map((name) => name.toLowerCase());
    if (new Set(lower).size !== lower.length) {
      return `Team ${key} has duplicate player names.`;
    }
  }
  if (!payload.rules.allowed_runs.length) {
    return "Choose at least one scoring shot value.";
  }
  if (!payload.rules.retirement_types.length) {
    return "Choose at least one retirement type.";
  }
  return null;
}

async function submit(event) {
  event.preventDefault();
  if (submitting) return;
  feedback(null);

  const payload = {
    preset: PRESET_KEY,
    rules: collectRules(),
    series_id: SERIES_ID,
    venue: value("venue") || null,
    team_a: { name: value("team_a_name"), players: squad("team_a_players") },
    team_b: { name: value("team_b_name"), players: squad("team_b_players") },
    toss: { winner: value("toss_winner"), decision: value("toss_decision") },
  };

  const problem = validate(payload);
  if (problem) {
    feedback({ type: "error", title: problem });
    return;
  }

  setBusy(true);
  try {
    const match = await apiPost("/api/matches", payload);
    createdMatchId = match.id;
    const started = await apiPost(`/api/matches/${match.id}/start`);
    window.location.assign(`/pages/live.html?match=${started.id}`);
  } catch (error) {
    setBusy(false);
    const link = createdMatchId
      ? ` Match #${createdMatchId} was created — open it from Match history.`
      : "";
    feedback({
      type: "error",
      title: `${error.message}${link}`,
      detail: describeDetails(error.details),
    });
  }
}

function bind() {
  const form = document.getElementById("setup-form");
  form.addEventListener("submit", submit);
  document
    .getElementById("players_per_team")
    .addEventListener("input", syncSquadHints);
  syncSquadHints();
}

async function init() {
  renderShell(document.body.dataset.nav || "home");
  try {
    const [data, series] = await Promise.all([
      fetchPresets(),
      SERIES_ID ? apiGet(`/api/series/${SERIES_ID}`) : Promise.resolve(null),
    ]);
    selectedSeries = series;
    const preset = data.presets.find((item) => item.key === PRESET_KEY);
    if (!preset) {
      root.innerHTML = `<p class="text-sm text-red-600 dark:text-red-300">Unknown format.</p>`;
      return;
    }
    root.innerHTML = formHtml(preset, selectedSeries);
    root.setAttribute("aria-busy", "false");
    bind();
  } catch (error) {
    root.innerHTML = `<p class="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-800 dark:text-red-200">${escapeHtml(error.message)}</p>`;
    root.setAttribute("aria-busy", "false");
  }
}

init();
