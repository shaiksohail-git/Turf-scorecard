import { apiGet } from "./api.js";
import { escapeHtml } from "./dom.js";
import { renderShell } from "../components/shell.js";

const root = document.getElementById("stats-root");
const card = "rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900";

function statCard(label, value, hint) {
  return `
    <div class="${card}">
      <p class="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">${escapeHtml(label)}</p>
      <p class="mt-1 text-2xl font-semibold tabular-nums">${value}</p>
      ${hint ? `<p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">${escapeHtml(hint)}</p>` : ""}
    </div>`;
}

function valueOrDash(value) {
  return value === null || value === undefined || value === "" ? "—" : value;
}

function decimal(value) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(2);
}

function leaderboard(title, rows, valueKey, valueLabel) {
  if (!rows.length) {
    return `
      <section class="${card}">
        <h2 class="text-base font-semibold">${escapeHtml(title)}</h2>
        <p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">Score a match to populate this leaderboard.</p>
      </section>`;
  }
  const best = Math.max(1, ...rows.map((row) => Number(row[valueKey]) || 0));
  return `
    <section class="${card}">
      <h2 class="text-base font-semibold">${escapeHtml(title)}</h2>
      <ol class="mt-3 space-y-3">
        ${rows
          .map(
            (row, index) => `
          <li>
            <div class="flex items-baseline justify-between gap-3 text-sm">
              <span class="truncate">
                <span class="mr-2 inline-block w-4 text-xs text-zinc-400">${index + 1}</span>
                <span class="font-medium">${escapeHtml(row.player_name)}</span>
                <span class="text-xs text-zinc-500 dark:text-zinc-400">· ${escapeHtml(row.team_name)}</span>
              </span>
              <span class="shrink-0 font-semibold tabular-nums">${row[valueKey]} <span class="text-xs font-normal text-zinc-500">${valueLabel}</span></span>
            </div>
            <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
              <div class="h-full rounded-full bg-primary-400" style="width:${Math.max(6, Math.round(((Number(row[valueKey]) || 0) / best) * 100))}%"></div>
            </div>
          </li>`,
          )
          .join("")}
      </ol>
    </section>`;
}

function playerTable(rows) {
  if (!rows.length) {
    return `<p class="py-3 text-sm text-zinc-500 dark:text-zinc-400">No player statistics yet.</p>`;
  }
  return `
    <div class="overflow-x-auto">
      <table class="w-full min-w-[64rem] text-sm">
        <caption class="sr-only">Player statistics</caption>
        <thead>
          <tr class="text-left text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            <th scope="col" class="py-2 pr-2 font-medium">Player</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">M</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Inns</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Runs</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">HS</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Avg</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">SR</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">4s</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">6s</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Wkts</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Bowl avg</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Econ</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Best</th>
            <th scope="col" class="py-2 pl-2 text-right font-medium">Fantasy</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
            <tr class="border-t border-zinc-200 dark:border-zinc-800">
              <td class="py-2 pr-2">
                <span class="font-medium">${escapeHtml(row.player_name)}</span>
                <span class="block text-xs text-zinc-500 dark:text-zinc-400">${escapeHtml(row.team_name)}</span>
              </td>
              <td class="py-2 px-2 text-right tabular-nums">${row.matches}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.innings}</td>
              <td class="py-2 px-2 text-right font-semibold tabular-nums">${row.runs}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.highest_score}</td>
              <td class="py-2 px-2 text-right tabular-nums">${decimal(row.batting_average)}</td>
              <td class="py-2 px-2 text-right tabular-nums">${decimal(row.strike_rate)}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.fours}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.sixes}</td>
              <td class="py-2 px-2 text-right font-semibold tabular-nums">${row.wickets}</td>
              <td class="py-2 px-2 text-right tabular-nums">${decimal(row.bowling_average)}</td>
              <td class="py-2 px-2 text-right tabular-nums">${decimal(row.economy)}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.best_bowling_wickets ? escapeHtml(row.best_bowling) : "—"}</td>
              <td class="py-2 pl-2 text-right font-semibold tabular-nums">${row.fantasy_points}</td>
            </tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function teamTable(rows) {
  if (!rows.length) {
    return `<p class="py-3 text-sm text-zinc-500 dark:text-zinc-400">No team statistics yet.</p>`;
  }
  return `
    <div class="overflow-x-auto">
      <table class="w-full min-w-[36rem] text-sm">
        <caption class="sr-only">Team statistics</caption>
        <thead>
          <tr class="text-left text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            <th scope="col" class="py-2 pr-2 font-medium">Team</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">M</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">W</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">L</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">T</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">High</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Low</th>
            <th scope="col" class="py-2 pl-2 text-right font-medium">Win %</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
            <tr class="border-t border-zinc-200 dark:border-zinc-800">
              <td class="py-2 pr-2 font-medium">${escapeHtml(row.team_name)}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.matches}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.wins}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.losses}</td>
              <td class="py-2 px-2 text-right tabular-nums">${row.ties}</td>
              <td class="py-2 px-2 text-right tabular-nums">${valueOrDash(row.highest_score)}</td>
              <td class="py-2 px-2 text-right tabular-nums">${valueOrDash(row.lowest_score)}</td>
              <td class="py-2 pl-2 text-right font-semibold tabular-nums">${decimal(row.win_percentage)}</td>
            </tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function render(overview, players, teams) {
  const totals = overview.totals;
  root.innerHTML = `
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      ${statCard("Matches", totals.matches, `${totals.matches_live} live · ${totals.matches_completed} done`)}
      ${statCard("Runs", totals.runs, "across all innings")}
      ${statCard("Wickets", totals.wickets, "all innings")}
      ${statCard("Players", totals.players, `${totals.teams} teams`)}
    </div>

    <div class="grid gap-4 lg:grid-cols-3">
      ${leaderboard("Top run scorers", overview.top_run_scorers, "runs", "runs")}
      ${leaderboard("Top wicket takers", overview.top_wicket_takers, "wickets", "wickets")}
      ${leaderboard("Fantasy points", overview.top_fantasy_scorers, "fantasy_points", "pts")}
    </div>

    <section class="${card}">
      <h2 class="text-base font-semibold">Player statistics</h2>
      <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Career totals across every scored match, rebuilt after each ball and correction.</p>
      <div class="mt-3">${playerTable(players)}</div>
    </section>

    <section class="${card}">
      <h2 class="text-base font-semibold">Team statistics</h2>
      <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Win percentage uses completed matches; highest and lowest scores include every innings played.</p>
      <div class="mt-3">${teamTable(teams)}</div>
    </section>

    <p class="text-xs text-zinc-500 dark:text-zinc-400">
      Fantasy points use the match format's configuration (T20 or short-format) and exclude fielding and captaincy.
    </p>`;
  root.setAttribute("aria-busy", "false");
}

async function init() {
  renderShell("stats");
  try {
    const [overview, players, teams] = await Promise.all([
      apiGet("/api/stats/overview?limit=5"),
      apiGet("/api/stats/players?limit=200"),
      apiGet("/api/stats/teams"),
    ]);
    render(overview, players, teams);
  } catch (error) {
    root.innerHTML = `<p class="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-800 dark:text-red-200">${escapeHtml(error.message)}</p>`;
    root.setAttribute("aria-busy", "false");
  }
}

init();
