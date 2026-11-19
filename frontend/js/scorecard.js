import { apiGet } from "./api.js";
import { escapeHtml } from "./dom.js";
import { renderShell } from "../components/shell.js";
import { formatDate, statusBadge, teamName } from "../components/ui.js";

const params = new URLSearchParams(window.location.search);
const matchId = Number(params.get("match"));
const root = document.getElementById("scorecard-root");
const card = "rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900";

const RETIREMENT_LABELS = {
  retired_not_out: "Retired not out",
  retired_out: "Retired out",
  retired_hurt: "Retired hurt",
};

function retirementLabel(type) {
  return RETIREMENT_LABELS[type] || String(type || "").replaceAll("_", " ");
}

function battingTable(lines) {
  if (!lines.length) {
    return `<p class="px-1 py-3 text-sm text-zinc-500 dark:text-zinc-400">No batter has faced a ball yet.</p>`;
  }
  return `
    <div class="overflow-x-auto">
      <table class="w-full min-w-[28rem] text-sm">
        <caption class="sr-only">Batting</caption>
        <thead>
          <tr class="text-left text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            <th scope="col" class="py-2 pr-2 font-medium">Batter</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">R</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">B</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">4s</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">6s</th>
            <th scope="col" class="py-2 pl-2 text-right font-medium">SR</th>
          </tr>
        </thead>
        <tbody>
          ${lines
            .map(
              (line) => `
            <tr class="border-t border-zinc-200 dark:border-zinc-800">
              <td class="py-2 pr-2">
                <span class="font-medium">${escapeHtml(line.name)}</span>
                <span class="block text-xs text-zinc-500 dark:text-zinc-400">
                  ${line.is_out ? escapeHtml(line.dismissal || "out") : line.balls ? "not out" : "did not bat"}${line.returned_to_bat ? " · returned" : ""}
                </span>
              </td>
              <td class="py-2 px-2 text-right font-semibold tabular-nums">${line.runs}</td>
              <td class="py-2 px-2 text-right tabular-nums">${line.balls}</td>
              <td class="py-2 px-2 text-right tabular-nums">${line.fours}</td>
              <td class="py-2 px-2 text-right tabular-nums">${line.sixes}</td>
              <td class="py-2 pl-2 text-right tabular-nums">${line.strike_rate.toFixed(2)}</td>
            </tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function bowlingTable(lines) {
  if (!lines.length) {
    return `<p class="px-1 py-3 text-sm text-zinc-500 dark:text-zinc-400">No bowling figures yet.</p>`;
  }
  return `
    <div class="overflow-x-auto">
      <table class="w-full min-w-[24rem] text-sm">
        <caption class="sr-only">Bowling</caption>
        <thead>
          <tr class="text-left text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            <th scope="col" class="py-2 pr-2 font-medium">Bowler</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">O</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">R</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">W</th>
            <th scope="col" class="py-2 pl-2 text-right font-medium">Econ</th>
          </tr>
        </thead>
        <tbody>
          ${lines
            .map(
              (line) => `
            <tr class="border-t border-zinc-200 dark:border-zinc-800">
              <td class="py-2 pr-2 font-medium">${escapeHtml(line.name)}</td>
              <td class="py-2 px-2 text-right tabular-nums">${escapeHtml(line.overs)}</td>
              <td class="py-2 px-2 text-right tabular-nums">${line.runs}</td>
              <td class="py-2 px-2 text-right font-semibold tabular-nums">${line.wickets}</td>
              <td class="py-2 pl-2 text-right tabular-nums">${line.economy.toFixed(2)}</td>
            </tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function fallOfWickets(rows) {
  if (!rows.length) {
    return `<p class="px-1 py-2 text-sm text-zinc-500 dark:text-zinc-400">No wickets yet.</p>`;
  }
  return `
    <div class="overflow-x-auto">
      <table class="w-full min-w-[22rem] text-sm">
        <caption class="sr-only">Fall of wickets</caption>
        <thead>
          <tr class="text-left text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            <th scope="col" class="py-2 pr-2 font-medium">Wicket</th>
            <th scope="col" class="py-2 px-2 font-medium">Batter</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Score</th>
            <th scope="col" class="py-2 pl-2 text-right font-medium">Over</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
            <tr class="border-t border-zinc-200 dark:border-zinc-800">
              <td class="py-2 pr-2 tabular-nums">${row.wicket}</td>
              <td class="py-2 px-2">${escapeHtml(row.batter_name)} <span class="text-xs text-zinc-500 dark:text-zinc-400">${escapeHtml(row.dismissal)}</span></td>
              <td class="py-2 px-2 text-right font-semibold tabular-nums">${row.runs}</td>
              <td class="py-2 pl-2 text-right tabular-nums">${escapeHtml(row.overs)}</td>
            </tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function partnershipsTable(rows) {
  if (!rows.length) {
    return `<p class="px-1 py-2 text-sm text-zinc-500 dark:text-zinc-400">No partnerships yet.</p>`;
  }
  return `
    <div class="overflow-x-auto">
      <table class="w-full min-w-[22rem] text-sm">
        <caption class="sr-only">Partnerships</caption>
        <thead>
          <tr class="text-left text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            <th scope="col" class="py-2 pr-2 font-medium">Batters</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Runs</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Balls</th>
            <th scope="col" class="py-2 pl-2 text-right font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
            <tr class="border-t border-zinc-200 dark:border-zinc-800">
              <td class="py-2 pr-2">${escapeHtml(row.batter_names.join(" & "))}</td>
              <td class="py-2 px-2 text-right font-semibold tabular-nums">${row.runs}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.balls}</td>
              <td class="py-2 pl-2 text-right text-xs text-zinc-500 dark:text-zinc-400">${row.unbeaten ? "unbeaten" : `wicket ${row.wicket}`}</td>
            </tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function retirementsList(rows) {
  return `
    <ul class="space-y-2">
      ${rows
        .map(
          (row) => `
        <li class="rounded-xl bg-zinc-100 px-3 py-2 dark:bg-zinc-800">
          <p class="text-sm font-medium">${escapeHtml(row.player_name)} · ${escapeHtml(retirementLabel(row.retirement_type))}</p>
          <p class="text-xs text-zinc-500 dark:text-zinc-400">
            ${row.reason ? escapeHtml(row.reason) : "No reason given"} · ${row.returned_at ? "returned to bat" : row.retirement_type === "retired_out" ? "out" : "did not return"}
          </p>
        </li>`,
        )
        .join("")}
    </ul>`;
}

function commentaryList(rows) {
  if (!rows.length) {
    return `<p class="px-1 py-2 text-sm text-zinc-500 dark:text-zinc-400">No balls recorded.</p>`;
  }
  return `
    <details class="mt-4 rounded-xl border border-zinc-200 dark:border-zinc-800">
      <summary class="cursor-pointer px-3 py-2 text-sm font-semibold">Ball-by-ball commentary (${rows.length})</summary>
      <ol class="max-h-72 space-y-2 overflow-y-auto border-t border-zinc-200 px-3 py-3 dark:border-zinc-800">
        ${rows
          .map(
            (row) => `
          <li class="text-sm"><span class="mr-2 font-semibold tabular-nums">${escapeHtml(row.over)}</span>${escapeHtml(row.text)}</li>`,
          )
          .join("")}
      </ol>
    </details>`;
}

function inningsSection(innings, match) {
  const extras = innings.extras;
  return `
    <section class="${card} mt-4">
      <header class="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 class="text-base font-semibold">${escapeHtml(teamName(match, innings.batting_team_id))}</h2>
          <p class="text-xs text-zinc-500 dark:text-zinc-400">Innings ${innings.number} · ${escapeHtml(innings.overs)} overs</p>
        </div>
        <p class="text-xl font-semibold tabular-nums">${innings.total_runs}/${innings.wickets}</p>
      </header>
      <p class="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
        Extras ${extras.total} (wd ${extras.wide}, nb ${extras.no_ball}, b ${extras.bye}, lb ${extras.leg_bye})
        · Run rate ${innings.run_rate.toFixed(2)}
      </p>
      <div class="mt-3">${battingTable(innings.batting)}</div>
      <h3 class="mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Bowling</h3>
      ${bowlingTable(innings.bowling)}
      <h3 class="mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Fall of wickets</h3>
      ${fallOfWickets(innings.fall_of_wickets || [])}
      <h3 class="mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Partnerships</h3>
      ${partnershipsTable(innings.partnerships || [])}
      ${(innings.retirements || []).length ? `<h3 class="mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Retirements</h3>${retirementsList(innings.retirements)}` : ""}
      ${commentaryList(innings.commentary || [])}
    </section>`;
}

function render(data) {
  const match = data.match;
  const liveLink =
    match.status === "live"
      ? `<a href="/pages/live.html?match=${match.id}" class="inline-flex min-h-11 items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300">Back to scoring</a>`
      : `<a href="/pages/match-type.html" class="inline-flex min-h-11 items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300">New match</a>`;

  root.innerHTML = `
    <a href="/pages/matches.html" class="mb-3 inline-block text-sm font-semibold text-zinc-500 hover:text-primary-700 dark:text-zinc-400 dark:hover:text-primary-300">← Matches</a>
    <header class="${card}">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-xs text-zinc-500 dark:text-zinc-400">${formatDate(match.date)}${match.venue ? ` · ${escapeHtml(match.venue)}` : ""}</p>
          <h1 class="mt-1 text-xl font-semibold tracking-tight">${escapeHtml(match.teams[0].name)} vs ${escapeHtml(match.teams[1].name)}</h1>
          <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">${escapeHtml(match.preset.replace("_", " "))} · ${match.overs} overs · ${match.players_per_team} a side · ${match.fantasy_config === "t20" ? "T20 fantasy" : "Short fantasy"}</p>
        </div>
        ${statusBadge(match.status)}
      </div>
      <p class="mt-3 text-sm font-semibold ${match.result_summary ? "text-primary-700 dark:text-primary-300" : "text-zinc-500 dark:text-zinc-400"}">
        ${escapeHtml(match.result_summary || (match.status === "live" ? "Match in progress" : "Awaiting first ball"))}
      </p>
      <div class="mt-4">${liveLink}</div>
    </header>
    ${data.innings.map((innings) => inningsSection(innings, match)).join("")}`;
  root.setAttribute("aria-busy", "false");
}

async function init() {
  renderShell("");
  if (!matchId || Number.isNaN(matchId)) {
    root.innerHTML = `<p class="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-800 dark:text-red-200">No match selected.</p>`;
    return;
  }
  try {
    render(await apiGet(`/api/matches/${matchId}/scorecard`));
  } catch (error) {
    root.innerHTML = `<p class="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-800 dark:text-red-200">${escapeHtml(error.message)}</p>`;
    root.setAttribute("aria-busy", "false");
  }
}

init();
