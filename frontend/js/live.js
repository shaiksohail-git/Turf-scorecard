import { apiGet, apiPost } from "./api.js";
import { describeDetails, escapeHtml, setMessage } from "./dom.js";
import {
  clearFailedDeliveries,
  enqueueDelivery,
  failedDeliveries,
  flushDeliveryQueue,
  pendingDeliveries,
  subscribeQueue,
} from "./offline.js";
import { renderShell } from "../components/shell.js";
import { statusBadge, teamName } from "../components/ui.js";

const params = new URLSearchParams(window.location.search);
const matchId = Number(params.get("match"));
const root = document.getElementById("live-root");

const view = {
  match: null,
  innings: null,
  state: null,
  deliveries: [],
  retirements: [],
  bowlerId: null,
  busy: false,
};

const card = "rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900";
const buttonBase =
  "rounded-xl border border-zinc-300 text-sm font-bold text-zinc-800 hover:border-primary-400 hover:text-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-400 dark:border-zinc-700 dark:text-zinc-100 dark:hover:text-primary-300";

const RETIREMENT_LABELS = {
  retired_not_out: "Retired not out",
  retired_out: "Retired out",
  retired_hurt: "Retired hurt",
};

function retirementLabel(type) {
  return RETIREMENT_LABELS[type] || String(type || "").replaceAll("_", " ");
}

function newEventId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `evt-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function playersOf(match) {
  const map = new Map();
  for (const key of ["team_a", "team_b"]) {
    for (const player of match[key]?.players || []) map.set(player.id, player);
  }
  return map;
}

function playerName(map, id) {
  return map.get(id)?.name || "Player";
}

function ballLabel(delivery) {
  if (delivery.is_wicket) return "W";
  if (delivery.extra_type === "wide") return `${delivery.total_runs}wd`;
  if (delivery.extra_type === "no_ball") return `${delivery.total_runs}nb`;
  if (delivery.extra_type === "bye") return `${delivery.extra_runs}b`;
  if (delivery.extra_type === "leg_bye") return `${delivery.extra_runs}lb`;
  return String(delivery.total_runs);
}

function bowlingPlayers(match, innings) {
  const team = match.team_a.id === innings.bowling_team_id ? match.team_a : match.team_b;
  return team.players || [];
}

function maxBowlerBalls() {
  const maxOvers = view.match?.rules?.max_overs_per_bowler;
  const ballsPerOver = view.match?.rules?.balls_per_over;
  return maxOvers && ballsPerOver ? maxOvers * ballsPerOver : null;
}

function bowlerUsage() {
  const usage = new Map();
  for (const delivery of view.deliveries) {
    if (!delivery.is_legal_ball) continue;
    usage.set(delivery.bowler_id, (usage.get(delivery.bowler_id) || 0) + 1);
  }
  return usage;
}

function scoreHeader(map) {
  const { match, innings, state } = view;
  const battingName = teamName(match, innings.batting_team_id);
  const bowlingName = teamName(match, innings.bowling_team_id);
  const chase =
    state.target && !state.is_complete
      ? `<p class="mt-2 rounded-lg bg-primary-400/10 px-3 py-2 text-sm font-medium text-primary-800 dark:text-primary-200">
           Need ${state.runs_needed} run${state.runs_needed === 1 ? "" : "s"} from ${state.balls_remaining} ball${state.balls_remaining === 1 ? "" : "s"}
         </p>`
      : "";

  const freeHit = state.pending_free_hit
    ? `<p class="mt-2 inline-flex rounded-full bg-amber-400/20 px-3 py-1 text-xs font-bold uppercase tracking-wide text-amber-700 dark:text-amber-300">Free hit</p>`
    : "";
  const bowlers = bowlingPlayers(view.match, innings);
  const usedBalls = bowlerUsage();
  const bowlerLimit = maxBowlerBalls();

  const batterRows = state.solo_mode
    ? [["Striker (solo)", state.striker_id, true]]
    : [
        ["Striker", state.striker_id, true],
        ["Non-striker", state.non_striker_id, false],
      ];
  const batters = batterRows
    .map(
      ([label, id, striking]) => `
        <div class="rounded-xl bg-zinc-100 px-3 py-2 dark:bg-zinc-800">
          <p class="text-xs text-zinc-500 dark:text-zinc-400">${label}</p>
          <p class="truncate text-sm font-semibold">${id ? escapeHtml(playerName(map, id)) : "—"}${striking && id ? ' <span aria-hidden="true">*</span>' : ""}</p>
        </div>`,
    )
    .join("");
  const soloNote = state.solo_mode
    ? `<p class="mt-2 rounded-lg bg-amber-400/15 px-3 py-2 text-sm font-medium text-amber-800 dark:text-amber-200">Solo batting — no partner, so strike does not rotate.</p>`
    : "";
  const paused =
    !state.can_score && !state.is_complete
      ? `<p class="mt-2 rounded-lg bg-amber-400/15 px-3 py-2 text-sm font-medium text-amber-800 dark:text-amber-200">Innings paused — return a retired batter to continue.</p>`
      : "";

  return `
    <section class="${card} p-4">
      <div class="flex items-start justify-between gap-2">
        <div>
          <p class="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">${escapeHtml(battingName)} batting</p>
          <p class="mt-1 text-3xl font-semibold tabular-nums">
            ${state.runs}/${state.wickets}
            <span class="text-base font-medium text-zinc-500 dark:text-zinc-400">(${escapeHtml(state.overs)})</span>
          </p>
          <p class="text-xs text-zinc-500 dark:text-zinc-400">vs ${escapeHtml(bowlingName)} · innings ${innings.number}</p>
        </div>
        ${statusBadge("live")}
      </div>
      ${chase}
      ${freeHit}
      ${soloNote}
      ${paused}
      <div class="mt-4 grid grid-cols-2 gap-2">${batters}</div>
      <div class="mt-4">
        <label for="bowler-select" class="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Bowler</label>
        <select id="bowler-select" class="mt-1 min-h-12 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950">
          ${bowlers
            .map((player) => {
              const reached = bowlerLimit !== null && (usedBalls.get(player.id) || 0) >= bowlerLimit;
              return `<option value="${player.id}" ${player.id === view.bowlerId ? "selected" : ""} ${reached ? "disabled" : ""}>${escapeHtml(player.name)}${reached ? " · over limit" : ""}</option>`;
            })
            .join("")}
        </select>
        <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Bowlers at their over limit are disabled.</p>
      </div>
    </section>`;
}

function retirementsPanel(map) {
  const enabled = view.match.rules?.retired_player_option !== false;
  if (!enabled && !view.retirements.length) return "";

  const history = view.retirements
    .map((retirement) => {
      const replacement = retirement.replacement_player_id
        ? playerName(map, retirement.replacement_player_id)
        : "No replacement";
      const status = retirement.returned_at
        ? "Returned to bat"
        : retirement.retirement_type === "retired_out"
          ? "Out — cannot return"
          : "Retired";
      const reason = retirement.reason ? ` · ${escapeHtml(retirement.reason)}` : "";
      const action = retirement.can_return
        ? `<button type="button" data-return="${retirement.id}" class="${buttonBase} min-h-11 shrink-0 px-3">Return</button>`
        : "";
      return `
        <li class="flex items-start justify-between gap-3 rounded-xl bg-zinc-100 px-3 py-2 dark:bg-zinc-800">
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold">${escapeHtml(retirement.player_name || "Player")}</p>
            <p class="text-xs text-zinc-500 dark:text-zinc-400">${escapeHtml(retirementLabel(retirement.retirement_type))} · ${status}${reason}</p>
            <p class="text-xs text-zinc-500 dark:text-zinc-400">Replacement: ${escapeHtml(replacement)}</p>
          </div>
          ${action}
        </li>`;
    })
    .join("");

  const crease = [];
  if (view.state.striker_id) crease.push(["Striker", view.state.striker_id]);
  if (view.state.non_striker_id) crease.push(["Non-striker", view.state.non_striker_id]);
  const types = view.match.rules?.retirement_types || Object.keys(RETIREMENT_LABELS);
  const replacements = (view.state.available_player_ids || [])
    .map((id) => `<option value="${id}">${escapeHtml(playerName(map, id))}</option>`)
    .join("");
  const form =
    enabled && view.state.striker_id
      ? `<button type="button" id="retire-toggle" class="${buttonBase} mt-3 min-h-11 w-full">Retire a batter</button>
         <div id="retire-panel" class="mt-3 rounded-xl border border-amber-400/40 bg-amber-400/5 p-3" hidden>
           <div class="grid gap-3 sm:grid-cols-2">
             <div>
               <label for="retire-player" class="block text-xs font-medium">Batter</label>
               <select id="retire-player" class="mt-1 min-h-11 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950">
                 ${crease.map(([label, id]) => `<option value="${id}">${label} · ${escapeHtml(playerName(map, id))}</option>`).join("")}
               </select>
             </div>
             <div>
               <label for="retire-type" class="block text-xs font-medium">Retirement</label>
               <select id="retire-type" class="mt-1 min-h-11 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950">
                 ${types.map((type) => `<option value="${type}">${escapeHtml(retirementLabel(type))}</option>`).join("")}
               </select>
             </div>
             <div>
               <label for="retire-replacement" class="block text-xs font-medium">Replacement</label>
               <select id="retire-replacement" class="mt-1 min-h-11 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950">
                 <option value="">Next eligible batter</option>
                 ${replacements}
               </select>
             </div>
             <div>
               <label for="retire-reason" class="block text-xs font-medium">Reason</label>
               <input id="retire-reason" maxlength="200" class="mt-1 min-h-11 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950" placeholder="Optional" />
             </div>
           </div>
           <button type="button" id="retire-confirm" class="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-amber-400 px-4 text-sm font-bold text-amber-950 hover:bg-amber-300">
             Confirm retirement
           </button>
         </div>`
      : "";
  const paused = !view.state.striker_id
    ? `<p class="mt-2 text-sm font-medium text-amber-700 dark:text-amber-300">No batter is at the crease. Return a retired batter to continue.</p>`
    : "";

  return `
    <section class="${card} mt-4 p-4">
      <div class="flex items-baseline justify-between gap-2">
        <h2 class="text-sm font-semibold">Retirements</h2>
        <span class="text-xs text-zinc-500 dark:text-zinc-400">${view.retirements.length} event${view.retirements.length === 1 ? "" : "s"}</span>
      </div>
      ${paused}
      ${history ? `<ul class="mt-3 space-y-2">${history}</ul>` : `<p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No retirements in this innings.</p>`}
      ${form}
      <div id="retirement-feedback" class="mt-3" hidden></div>
    </section>`;
}

function overStrip() {
  const recent = view.deliveries.slice(-6);
  if (!recent.length) return "";
  return `
    <section class="mt-3 flex items-center gap-2 overflow-x-auto pb-1" aria-label="This over">
      <span class="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">This over</span>
      ${recent
        .map(
          (delivery) => `<span class="inline-flex h-9 min-w-9 items-center justify-center rounded-full border px-2 text-xs font-bold ${
            delivery.is_wicket
              ? "border-red-400/60 bg-red-400/15 text-red-700 dark:text-red-300"
              : "border-zinc-300 text-zinc-700 dark:border-zinc-700 dark:text-zinc-200"
          }">${escapeHtml(ballLabel(delivery))}</span>`,
        )
        .join("")}
    </section>`;
}

function pad() {
  const allowed = view.match.rules.allowed_runs;
  return `
    <section class="${card} mt-4 p-4">
      <h2 class="text-sm font-semibold">Score this ball</h2>
      <div class="mt-3 grid grid-cols-4 gap-2">
        ${allowed
          .map(
            (run) => `<button type="button" data-runs="${run}"
              class="${buttonBase} min-h-14 text-lg ${run === 4 || run === 6 ? "border-primary-400/70 text-primary-800 dark:text-primary-200" : ""}">${run}</button>`,
          )
          .join("")}
      </div>

      <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <button type="button" data-extra="wide" class="${buttonBase} min-h-12">Wide</button>
        <button type="button" data-extra="no_ball" class="${buttonBase} min-h-12">No ball</button>
        <button type="button" data-extra="bye" class="${buttonBase} min-h-12">Bye</button>
        <button type="button" data-extra="leg_bye" class="${buttonBase} min-h-12">Leg bye</button>
      </div>

      <div class="mt-3 flex items-center gap-3">
        <label for="extra-runs" class="text-sm font-medium">Extra runs</label>
        <input id="extra-runs" type="number" inputmode="numeric" min="0" max="4" value="0"
          class="min-h-11 w-20 rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" />
        <p class="text-xs text-zinc-500 dark:text-zinc-400">Added to wide, no-ball, bye or leg bye.</p>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2">
        <button type="button" id="wicket-toggle" class="${buttonBase} min-h-12 border-red-400/60 text-red-700 dark:text-red-300">Wicket</button>
        <button type="button" id="undo-button" class="${buttonBase} min-h-12">Undo</button>
      </div>

      <div id="wicket-panel" class="mt-3 rounded-xl border border-red-400/40 bg-red-500/5 p-3" hidden>
        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label for="wicket-type" class="block text-xs font-medium">Dismissal</label>
            <select id="wicket-type" class="mt-1 min-h-11 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950">
              <option value="bowled">Bowled</option>
              <option value="caught">Caught</option>
              <option value="lbw">LBW</option>
              <option value="stumped">Stumped</option>
              <option value="run_out">Run out</option>
              <option value="hit_wicket">Hit wicket</option>
            </select>
          </div>
          <div>
            <label for="dismissed-role" class="block text-xs font-medium">Batter out</label>
            <select id="dismissed-role" class="mt-1 min-h-11 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-950">
              <option value="striker">Striker</option>
              <option value="non_striker">Non-striker</option>
            </select>
          </div>
        </div>
        <button type="button" id="wicket-confirm"
          class="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-red-500 px-4 text-sm font-bold text-white hover:bg-red-400">
          Confirm wicket
        </button>
      </div>

      <div id="live-feedback" class="mt-3" hidden></div>
    </section>`;
}

function renderLive(map) {
  root.innerHTML = `
    ${backLink()}
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h1 class="text-xl font-semibold tracking-tight">${escapeHtml(teamName(view.match, view.innings.batting_team_id))} vs ${escapeHtml(teamName(view.match, view.innings.bowling_team_id))}</h1>
      <a href="/pages/scorecard.html?match=${view.match.id}" class="text-sm font-semibold text-primary-700 hover:underline dark:text-primary-300">Scorecard</a>
    </div>
    <div id="queue-status" class="mt-3 hidden rounded-xl border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm font-medium text-amber-800 dark:text-amber-200" role="status"></div>
    ${scoreHeader(map)}
    ${retirementsPanel(map)}
    ${overStrip()}
    ${pad()}`;
  updateQueueStatus();
  bindPad();
  bindRetirements();
  if (!view.state.can_score) setPadEnabled(false);
}

function renderFinished() {
  const { match } = view;
  root.innerHTML = `
    ${backLink()}
    <section class="${card} p-5">
      <div class="flex items-center justify-between gap-2">
        <h1 class="text-xl font-semibold tracking-tight">${escapeHtml(match.teams[0].name)} vs ${escapeHtml(match.teams[1].name)}</h1>
        ${statusBadge(match.status)}
      </div>
      <p class="mt-4 text-lg font-semibold text-primary-700 dark:text-primary-300">
        ${escapeHtml(match.result_summary || "Match finished")}
      </p>
      <div class="mt-4 space-y-2">
        ${match.innings
          .map(
            (innings) => `
          <div class="flex items-baseline justify-between gap-3 text-sm">
            <span>${escapeHtml(teamName(match, innings.batting_team_id))}</span>
            <span class="tabular-nums font-semibold">${innings.runs}/${innings.wickets} (${escapeHtml(innings.overs)})</span>
          </div>`,
          )
          .join("")}
      </div>
      <a href="/pages/scorecard.html?match=${match.id}"
        class="mt-5 inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300">
        Open full scorecard
      </a>
    </section>
    <section class="mt-4 grid gap-3 sm:grid-cols-2">
      <a href="/pages/match-type.html" class="${card} p-4 text-sm font-semibold hover:border-primary-400">Start a new match</a>
      <a href="/pages/matches.html" class="${card} p-4 text-sm font-semibold hover:border-primary-400">Match history</a>
    </section>`;
}

function backLink() {
  return `<a href="/pages/matches.html" class="mb-3 inline-block text-sm font-semibold text-zinc-500 hover:text-primary-700 dark:text-zinc-400 dark:hover:text-primary-300">← Matches</a>`;
}

function bowlerValue() {
  const select = document.getElementById("bowler-select");
  return select ? Number(select.value) : view.bowlerId;
}

function setPadEnabled(enabled) {
  root.querySelectorAll("button[data-runs], button[data-extra], #wicket-toggle, #undo-button, #wicket-confirm, #bowler-select, #extra-runs, #retire-toggle, #retire-confirm, #retire-player, #retire-type, #retire-replacement, #retire-reason").forEach(
    (element) => {
      element.disabled = !enabled;
    },
  );
}

function extraRuns() {
  const input = document.getElementById("extra-runs");
  const value = Number(input?.value || 0);
  return Number.isFinite(value) ? Math.max(0, Math.min(4, value)) : 0;
}

async function submitAction(path, payload, feedbackId) {
  if (view.busy) return;
  if (!navigator.onLine) {
    const feedback = document.getElementById(feedbackId);
    setMessage(feedback, {
      type: "error",
      title: "This action needs a connection.",
      detail: "Deliveries are saved offline; undo and retirement changes sync only while online.",
    });
    return;
  }
  view.busy = true;
  setPadEnabled(false);
  const feedback = document.getElementById(feedbackId);
  setMessage(feedback, null);
  try {
    await apiPost(path, payload);
    await load();
  } catch (error) {
    view.busy = false;
    setPadEnabled(Boolean(view.state?.can_score));
    setMessage(feedback, {
      type: "error",
      title: error.message,
      detail: describeDetails(error.details),
    });
  }
}

async function send(payload) {
  if (view.busy) return;
  const eventPayload = {
    ...payload,
    bowler_id: bowlerValue(),
    client_event_id: newEventId(),
  };
  enqueueDelivery(view.innings.innings_id, eventPayload);
  view.busy = true;
  setPadEnabled(false);
  const feedback = document.getElementById("live-feedback");
  setMessage(feedback, null);

  if (!navigator.onLine) {
    view.busy = false;
    setPadEnabled(Boolean(view.state?.can_score));
    updateQueueStatus();
    setMessage(feedback, {
      type: "info",
      title: "Saved offline. This ball will sync when you reconnect.",
      detail: `${pendingDeliveries()} delivery${pendingDeliveries() === 1 ? "" : "ies"} waiting on this device.`,
    });
    return;
  }

  let rejectedMessage = null;
  const result = await flushDeliveryQueue({
    onConflict: (error) => {
      rejectedMessage = {
        type: "error",
        title: "A queued ball was rejected.",
        detail: `${error.message} It was moved to the local recovery list so later balls can sync.`,
      };
    },
    onError: (error) => {
      rejectedMessage = {
        type: "error",
        title: "A queued ball could not be sent.",
        detail: error.message,
      };
    },
  });
  view.busy = false;
  if (result.pending === 0) {
    await load();
    if (rejectedMessage) setMessage(document.getElementById("live-feedback"), rejectedMessage);
  } else {
    setPadEnabled(Boolean(view.state?.can_score));
    updateQueueStatus();
    if (rejectedMessage) setMessage(feedback, rejectedMessage);
  }
}

function updateQueueStatus() {
  const node = document.getElementById("queue-status");
  if (!node) return;
  const count = pendingDeliveries();
  const failed = failedDeliveries().length;
  node.hidden = count === 0 && failed === 0;
  if (node.hidden) {
    node.textContent = "";
    return;
  }
  const waiting = count
    ? `${count} delivery${count === 1 ? "" : "ies"} waiting to sync. Keep this page open and reconnect.`
    : "";
  const rejected = failed
    ? `${failed} rejected ball${failed === 1 ? "" : "s"} kept locally.`
    : "";
  const action = failed
    ? `<button id="clear-failed" type="button" class="min-h-9 rounded-lg border border-current px-2 text-xs font-bold">Discard rejected</button>`
    : "";
  node.innerHTML = `<div class="flex flex-wrap items-center justify-between gap-2"><span>${[waiting, rejected].filter(Boolean).join(" ")}</span>${action}</div>`;
  document.getElementById("clear-failed")?.addEventListener("click", () => {
    if (!window.confirm("Discard the locally saved rejected balls? This cannot be undone.")) return;
    clearFailedDeliveries();
    updateQueueStatus();
  });
}

function bindRetirements() {
  const toggle = document.getElementById("retire-toggle");
  const panel = document.getElementById("retire-panel");
  toggle?.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) document.getElementById("retire-player")?.focus();
  });

  root.querySelectorAll("[data-return]").forEach((button) => {
    button.addEventListener("click", () => {
      submitAction(
        `/api/innings/${view.innings.innings_id}/retirements/${button.dataset.return}/return`,
        {},
        "retirement-feedback",
      );
    });
  });

  document.getElementById("retire-confirm")?.addEventListener("click", () => {
    const playerId = Number(document.getElementById("retire-player")?.value);
    const retirementType = document.getElementById("retire-type")?.value;
    const replacement = Number(document.getElementById("retire-replacement")?.value || 0);
    const reason = document.getElementById("retire-reason")?.value?.trim();
    const payload = { player_id: playerId, retirement_type: retirementType };
    if (replacement) payload.replacement_player_id = replacement;
    if (reason) payload.reason = reason;
    submitAction(
      `/api/innings/${view.innings.innings_id}/retirements`,
      payload,
      "retirement-feedback",
    );
  });
}

function bindPad() {
  const feedback = document.getElementById("live-feedback");

  const bowlerSelect = document.getElementById("bowler-select");
  if (bowlerSelect) {
    bowlerSelect.addEventListener("change", () => {
      view.bowlerId = Number(bowlerSelect.value);
    });
    view.bowlerId = Number(bowlerSelect.value) || view.bowlerId;
  }

  root.querySelectorAll("button[data-runs]").forEach((button) => {
    button.addEventListener("click", () => send({ runs_off_bat: Number(button.dataset.runs) }));
  });

  root.querySelectorAll("button[data-extra]").forEach((button) => {
    button.addEventListener("click", () => {
      const type = button.dataset.extra;
      const runs = extraRuns();
      if (type === "bye" || type === "leg_bye") {
        send({ extra_type: type, extra_runs: Math.max(1, runs) });
      } else {
        send({ extra_type: type, extra_runs: runs });
      }
    });
  });

  const panel = document.getElementById("wicket-panel");
  document.getElementById("wicket-toggle")?.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) document.getElementById("wicket-type")?.focus();
  });

  const typeSelect = document.getElementById("wicket-type");
  const roleSelect = document.getElementById("dismissed-role");
  typeSelect?.addEventListener("change", () => {
    if (typeSelect.value !== "run_out") {
      roleSelect.value = "striker";
      roleSelect.disabled = true;
    } else {
      roleSelect.disabled = false;
    }
  });
  roleSelect.disabled = true;

  document.getElementById("wicket-confirm")?.addEventListener("click", () => {
    send({
      runs_off_bat: 0,
      is_wicket: true,
      wicket_type: typeSelect.value,
      dismissed_player: roleSelect.value,
    });
  });

  document.getElementById("undo-button")?.addEventListener("click", async () => {
    if (view.busy) return;
    if (!navigator.onLine) {
      setMessage(feedback, {
        type: "error",
        title: "Undo needs a connection.",
        detail: "Reconnect before changing an already-scored ball.",
      });
      return;
    }
    view.busy = true;
    setPadEnabled(false);
    setMessage(feedback, null);
    try {
      await apiPost(`/api/innings/${view.innings.innings_id}/deliveries/undo`, {
        reason: "Undo from scoring pad",
      });
      await load();
    } catch (error) {
      view.busy = false;
      setPadEnabled(Boolean(view.state?.can_score));
      setMessage(feedback, {
        type: "error",
        title: error.message,
        detail: describeDetails(error.details),
      });
    }
  });
}

function renderDraft() {
  const match = view.match;
  root.innerHTML = `
    ${backLink()}
    <section class="${card} p-5">
      <h1 class="text-xl font-semibold tracking-tight">${escapeHtml(match.teams[0].name)} vs ${escapeHtml(match.teams[1].name)}</h1>
      <p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">This match has not started yet.</p>
      <button id="start-match" type="button"
        class="mt-4 inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300">
        Start match
      </button>
      <div id="draft-feedback" class="mt-3" hidden></div>
    </section>`;
  document.getElementById("start-match")?.addEventListener("click", async (event) => {
    event.currentTarget.disabled = true;
    try {
      await apiPost(`/api/matches/${matchId}/start`);
      await load();
    } catch (error) {
      event.currentTarget.disabled = false;
      setMessage(document.getElementById("draft-feedback"), {
        type: "error",
        title: error.message,
      });
    }
  });
}

function renderError(message) {
  root.innerHTML = `
    ${backLink()}
    <p class="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-800 dark:text-red-200">${escapeHtml(message)}</p>
    <a href="/pages/match-type.html" class="mt-4 inline-flex min-h-12 items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950">Start a new match</a>`;
}

async function load() {
  if (!matchId || Number.isNaN(matchId)) {
    renderError("No match selected. Open a match from Match history.");
    return;
  }

  try {
    let rejected = null;
    await flushDeliveryQueue({
      onConflict: (error) => {
        rejected = error;
      },
      onError: () => {},
    });
    await loadMatch();
    if (rejected) {
      setMessage(document.getElementById("live-feedback"), {
        type: "error",
        title: "A queued ball was rejected.",
        detail: `${rejected.message} It was moved to the local recovery list.`,
      });
    }
  } catch (error) {
    renderError(error.message);
  }
}

async function loadMatch() {
  if (!matchId || Number.isNaN(matchId)) {
    renderError("No match selected. Open a match from Match history.");
    return;
  }

  try {
    const match = await apiGet(`/api/matches/${matchId}`);
    view.match = match;

    if (match.status === "draft") {
      renderDraft();
      return;
    }
    if (match.status === "completed" || match.status === "abandoned") {
      renderFinished();
      return;
    }

    const liveInnings = match.innings.find((innings) => innings.status === "live");
    if (!liveInnings) {
      renderFinished();
      return;
    }

    view.innings = liveInnings;
    const [state, deliveries, retirements] = await Promise.all([
      apiGet(`/api/innings/${liveInnings.innings_id}`),
      apiGet(`/api/innings/${liveInnings.innings_id}/deliveries`),
      apiGet(`/api/innings/${liveInnings.innings_id}/retirements`),
    ]);
    view.state = state;
    view.deliveries = deliveries;
    view.retirements = retirements;
    view.busy = false;

    const bowlers = bowlingPlayers(match, liveInnings);
    const bowlerLimit = maxBowlerBalls();
    const usedBalls = bowlerUsage();
    const eligible = bowlers.filter(
      (player) => bowlerLimit === null || (usedBalls.get(player.id) || 0) < bowlerLimit,
    );
    const preferred = view.bowlerId || state.last_bowler_id;
    view.bowlerId = eligible.some((player) => player.id === preferred)
      ? preferred
      : eligible[0]?.id ?? state.last_bowler_id;

    const map = playersOf(match);
    renderLive(map);
  } catch (error) {
    renderError(error.message);
  } finally {
    root.setAttribute("aria-busy", "false");
  }
}

renderShell("");
subscribeQueue(() => updateQueueStatus());
window.addEventListener("gully:online", async () => {
  await load();
});
window.addEventListener("gully:sync", async () => {
  await load();
});
load();
