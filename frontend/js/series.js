import { apiGet, apiPatch, fetchPresets } from "./api.js";
import { describeDetails, escapeHtml, setMessage } from "./dom.js";
import { renderShell } from "../components/shell.js";
import { errorPanel, formatDate } from "../components/ui.js";

const root = document.getElementById("series-root");
const params = new URLSearchParams(window.location.search);
const seriesId = Number(params.get("id")) || null;
const card = "rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900";
const tableHead =
  "text-left text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400";
const rowBorder = "border-t border-zinc-200 dark:border-zinc-800";

let series = null;
let presets = [];
let editing = false;

function dash(value) {
  return value === null || value === undefined || value === "" ? "—" : value;
}

function decimal(value) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(2);
}

function presetLabel(key) {
  if (!key) return "Mixed formats";
  return presets.find((preset) => preset.key === key)?.label || key;
}

function initials(value) {
  return String(value || "?")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function dateRange(start, end) {
  if (!start && !end) return "Dates not set";
  if (start && end) return `${formatDate(start)} – ${formatDate(end)}`;
  return formatDate(start || end);
}

function playerLine(players) {
  return players.length ? players.join(", ") : "No players recorded";
}

function statCard(label, value, hint) {
  return `
    <div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-950">
      <p class="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">${escapeHtml(label)}</p>
      <p class="mt-1 text-2xl font-semibold tabular-nums">${escapeHtml(value)}</p>
      ${hint ? `<p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">${escapeHtml(hint)}</p>` : ""}
    </div>`;
}

function teamChips() {
  if (!series.teams.length) {
    return `<p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No series roster yet. Teams are derived from linked matches.</p>`;
  }
  return `
    <div class="mt-3 grid gap-2 sm:grid-cols-2">
      ${series.teams
        .map(
          (team) => `
        <div class="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
          <div class="flex items-center gap-2">
            <span class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-primary-400/15 text-xs font-bold text-primary-700 dark:text-primary-300">${escapeHtml(initials(team.name))}</span>
            <p class="text-sm font-semibold">${escapeHtml(team.name)}</p>
          </div>
          <p class="mt-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">${escapeHtml(playerLine(team.players || []))}</p>
        </div>`,
        )
        .join("")}
    </div>`;
}

function awardsSection() {
  const awards = series.awards || {};
  const cards = [];
  const addAward = (award) => {
    if (!award) return;
    const winners = award.winners || [];
    cards.push(`
      <div class="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
        <div class="flex items-baseline justify-between gap-2">
          <p class="text-sm font-semibold">${escapeHtml(award.label)}</p>
          ${award.tied ? `<span class="rounded-full bg-amber-400/15 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300">Tied</span>` : ""}
        </div>
        ${
          winners.length
            ? `<div class="mt-2 space-y-1.5">${winners
                .map(
                  (winner) => `
              <div class="flex items-baseline justify-between gap-3 text-sm">
                <span class="truncate font-medium">${escapeHtml(winner.player_name)} <span class="text-xs font-normal text-zinc-500">· ${escapeHtml(winner.team_name)}</span></span>
                <span class="shrink-0 text-xs font-semibold tabular-nums">${escapeHtml(winner.points)} pts</span>
              </div>`,
                )
                .join("")}</div>`
            : `<p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">Awaiting a completed match.</p>`
        }
      </div>`);
  };
  addAward(awards.player_of_series);
  addAward(awards.best_batter);
  addAward(awards.best_bowler);

  const pom = awards.player_of_match || [];
  return `
    <section class="${card}">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 class="text-base font-semibold">Awards</h2>
          <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Player of the Series is the highest cumulative fantasy total across completed matches.</p>
        </div>
        <span class="text-xs text-zinc-500 dark:text-zinc-400">${awards.player_of_match?.length || 0} match awards</span>
      </div>
      <div class="mt-3 grid gap-3 lg:grid-cols-3">${cards.join("")}</div>
      <div class="mt-4">
        <h3 class="text-sm font-semibold">Player of the Match</h3>
        ${
          pom.length
            ? `<div class="mt-2 divide-y divide-zinc-200 dark:divide-zinc-800">${pom
                .map(
                  (award) => `
              <div class="flex flex-wrap items-baseline justify-between gap-2 py-2 text-sm">
                <span class="text-zinc-500 dark:text-zinc-400">${escapeHtml(award.match_label)}</span>
                <span class="font-medium">${award.winners.map((winner) => escapeHtml(winner.player_name)).join(" & ")}${award.tied ? " (tied)" : ""}</span>
                <span class="text-xs tabular-nums text-zinc-500">${escapeHtml(award.value)} pts</span>
              </div>`,
                )
                .join("")}</div>`
            : `<p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No completed matches yet.</p>`
        }
      </div>
    </section>`;
}

function standingsSection() {
  const rows = series.standings || [];
  return `
    <section class="${card}">
      <h2 class="text-base font-semibold">Standings</h2>
      <div class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[34rem] text-sm">
          <caption class="sr-only">Series standings</caption>
          <thead><tr class="${tableHead}">
            <th scope="col" class="py-2 pr-2 font-medium">#</th>
            <th scope="col" class="py-2 pr-2 font-medium">Team</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">P</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">W</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">L</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">T</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Pts</th>
            <th scope="col" class="py-2 pl-2 text-right font-medium">Win %</th>
          </tr></thead>
          <tbody>
            ${
              rows.length
                ? rows
                    .map(
                      (row) => `
                <tr class="${rowBorder}">
                  <td class="py-2 pr-2 text-zinc-400">${row.rank}</td>
                  <td class="py-2 pr-2 font-medium">${escapeHtml(row.team_name)}</td>
                  <td class="py-2 px-2 text-right tabular-nums">${row.played}</td>
                  <td class="py-2 px-2 text-right tabular-nums">${row.wins}</td>
                  <td class="py-2 px-2 text-right tabular-nums">${row.losses}</td>
                  <td class="py-2 px-2 text-right tabular-nums">${row.ties}</td>
                  <td class="py-2 px-2 text-right font-semibold tabular-nums">${row.points}</td>
                  <td class="py-2 pl-2 text-right tabular-nums">${decimal(row.win_percentage)}</td>
                </tr>`,
                    )
                    .join("")
                : `<tr><td colspan="8" class="py-3 text-sm text-zinc-500 dark:text-zinc-400">No completed matches yet.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </section>`;
}

function mvpSection() {
  const rows = series.mvp_leaderboard || [];
  return `
    <section class="${card}">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-base font-semibold">Fantasy / MVP leaderboard</h2>
        <p class="text-xs text-zinc-500 dark:text-zinc-400">Batting + bowling only · fielding and captaincy excluded</p>
      </div>
      <div class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[38rem] text-sm">
          <caption class="sr-only">Fantasy MVP leaderboard</caption>
          <thead><tr class="${tableHead}">
            <th scope="col" class="py-2 pr-2 font-medium">#</th>
            <th scope="col" class="py-2 pr-2 font-medium">Player</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">M</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Bat</th>
            <th scope="col" class="py-2 px-2 text-right font-medium">Bowl</th>
            <th scope="col" class="py-2 pl-2 text-right font-medium">Total</th>
          </tr></thead>
          <tbody>
            ${
              rows.length
                ? rows
                    .slice(0, 20)
                    .map(
                      (row) => `
                <tr class="${rowBorder}">
                  <td class="py-2 pr-2 text-zinc-400">${row.rank}</td>
                  <td class="py-2 pr-2">
                    <span class="font-medium">${escapeHtml(row.player_name)}</span>
                    <span class="block text-xs text-zinc-500 dark:text-zinc-400">${escapeHtml(row.team_name)}</span>
                  </td>
                  <td class="py-2 px-2 text-right tabular-nums">${row.matches}</td>
                  <td class="py-2 px-2 text-right tabular-nums">${row.batting_points}</td>
                  <td class="py-2 px-2 text-right tabular-nums">${row.bowling_points}</td>
                  <td class="py-2 pl-2 text-right font-semibold tabular-nums">${row.fantasy_points}</td>
                </tr>`,
                    )
                    .join("")
                : `<tr><td colspan="6" class="py-3 text-sm text-zinc-500 dark:text-zinc-400">Fantasy points appear after the first completed match.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </section>`;
}

function boardTable(title, board, columns) {
  if (!board) return "";
  return `
    <section class="${card}">
      <div class="flex items-baseline justify-between gap-2">
        <h3 class="text-sm font-semibold">${escapeHtml(title)}</h3>
        ${board.qualification ? `<span class="max-w-48 text-right text-[11px] text-zinc-500 dark:text-zinc-400">${escapeHtml(board.qualification)}</span>` : ""}
      </div>
      ${
        board.rows.length
          ? `<div class="mt-2 overflow-x-auto"><table class="w-full min-w-[22rem] text-sm">
              <caption class="sr-only">${escapeHtml(title)}</caption>
              <thead><tr class="${tableHead}">
                <th scope="col" class="py-2 pr-2 font-medium">#</th>
                <th scope="col" class="py-2 pr-2 font-medium">Player</th>
                ${columns.map((column) => `<th scope="col" class="py-2 pl-2 text-right font-medium">${escapeHtml(column.label)}</th>`).join("")}
              </tr></thead>
              <tbody>${board.rows
                .slice(0, 10)
                .map(
                  (row, index) => `
                <tr class="${rowBorder}">
                  <td class="py-2 pr-2 text-zinc-400">${index + 1}</td>
                  <td class="py-2 pr-2">
                    <span class="font-medium">${escapeHtml(row.player_name)}</span>
                    <span class="block text-[11px] text-zinc-500 dark:text-zinc-400">${escapeHtml(row.team_name)}</span>
                  </td>
                  ${columns
                    .map(
                      (column) =>
                        `<td class="py-2 pl-2 text-right tabular-nums">${escapeHtml(column.value(row))}</td>`,
                    )
                    .join("")}
                </tr>`,
                )
                .join("")}</tbody>
            </table></div>`
          : `<p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No qualified players yet.</p>`
      }
    </section>`;
}

function battingSection() {
  const boards = series.batting_leaderboards || {};
  return `
    <section>
      <div class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-base font-semibold">Batting leaderboards</h2>
        <span class="text-xs text-zinc-500 dark:text-zinc-400">Rate boards use qualification thresholds</span>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        ${boardTable("Most runs", boards.runs, [
          { label: "Runs", value: (row) => row.runs },
          { label: "HS", value: (row) => row.highest_score },
        ])}
        ${boardTable("Highest score", boards.highest_score, [
          { label: "HS", value: (row) => row.highest_score },
          { label: "Runs", value: (row) => row.runs },
        ])}
        ${boardTable("Best batting average", boards.average, [
          { label: "Avg", value: (row) => decimal(row.batting_average) },
          { label: "Runs", value: (row) => row.runs },
          { label: "Inns", value: (row) => row.batting_innings },
        ])}
        ${boardTable("Best strike rate", boards.strike_rate, [
          { label: "SR", value: (row) => decimal(row.strike_rate) },
          { label: "Balls", value: (row) => row.balls },
        ])}
        ${boardTable("Most fours", boards.fours, [{ label: "4s", value: (row) => row.fours }])}
        ${boardTable("Most sixes", boards.sixes, [{ label: "6s", value: (row) => row.sixes }])}
        ${boardTable("Most fifties", boards.fifties, [{ label: "50s", value: (row) => row.fifties }])}
        ${boardTable("Most centuries", boards.centuries, [{ label: "100s", value: (row) => row.centuries }])}
      </div>
    </section>`;
}

function bowlingSection() {
  const boards = series.bowling_leaderboards || {};
  return `
    <section>
      <div class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-base font-semibold">Bowling leaderboards</h2>
        <span class="text-xs text-zinc-500 dark:text-zinc-400">Rate boards use qualification thresholds</span>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        ${boardTable("Most wickets", boards.wickets, [
          { label: "Wkts", value: (row) => row.wickets },
          { label: "Best", value: (row) => dash(row.best_bowling) },
        ])}
        ${boardTable("Best economy", boards.economy, [
          { label: "Econ", value: (row) => decimal(row.economy) },
          { label: "Balls", value: (row) => row.bowling_balls },
        ])}
        ${boardTable("Best bowling figures", boards.best_figures, [
          { label: "Best", value: (row) => dash(row.best_bowling) },
          { label: "Wkts", value: (row) => row.wickets },
        ])}
        ${boardTable("Best bowling average", boards.average, [
          { label: "Avg", value: (row) => decimal(row.bowling_average) },
          { label: "Wkts", value: (row) => row.wickets },
        ])}
        ${boardTable("Best bowling strike rate", boards.strike_rate, [
          { label: "SR", value: (row) => decimal(row.bowling_strike_rate) },
          { label: "Balls", value: (row) => row.bowling_balls },
        ])}
        ${boardTable("Most maiden overs", boards.maidens, [{ label: "Maidens", value: (row) => row.maidens }])}
        ${boardTable("Most dot balls", boards.dot_balls, [{ label: "Dots", value: (row) => row.dot_balls }])}
      </div>
    </section>`;
}

function recentSection() {
  const results = series.recent_results || [];
  return `
    <section class="${card}">
      <h2 class="text-base font-semibold">Recent results</h2>
      ${
        results.length
          ? `<div class="mt-3 divide-y divide-zinc-200 dark:divide-zinc-800">${results
              .map(
                (result) => `
            <a href="/pages/scorecard.html?match=${result.match_id}" class="block py-3 hover:text-primary-700 dark:hover:text-primary-300">
              <div class="flex flex-wrap items-baseline justify-between gap-2">
                <span class="text-sm font-medium">${escapeHtml(result.label)}</span>
                <span class="text-xs text-zinc-500 dark:text-zinc-400">${escapeHtml(formatDate(result.completed_at))}</span>
              </div>
              <p class="mt-1 text-sm text-primary-700 dark:text-primary-300">${escapeHtml(result.result_summary || "Result recorded")}</p>
              <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">${result.innings
                .map((innings) => `${escapeHtml(innings.team_name)} ${innings.runs}/${innings.wickets} (${innings.overs})`)
                .join(" · ")}</p>
            </a>`,
              )
              .join("")}</div>`
          : `<p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">Complete a match to see its result here.</p>`
      }
    </section>`;
}

function matchFantasySection() {
  const matches = series.match_fantasy || [];
  if (!matches.length) return "";
  return `
    <details class="${card}">
      <summary class="cursor-pointer text-base font-semibold">Match-wise fantasy points</summary>
      <div class="mt-3 space-y-4">
        ${matches
          .map(
            (match) => `
          <div>
            <p class="text-sm font-semibold">${escapeHtml(match.match_label)}</p>
            <div class="mt-1 overflow-x-auto"><table class="w-full min-w-[26rem] text-sm">
              <thead><tr class="${tableHead}">
                <th scope="col" class="py-1 pr-2 font-medium">Player</th>
                <th scope="col" class="py-1 px-2 text-right font-medium">Bat</th>
                <th scope="col" class="py-1 px-2 text-right font-medium">Bowl</th>
                <th scope="col" class="py-1 pl-2 text-right font-medium">Total</th>
              </tr></thead>
              <tbody>${match.players
                .map(
                  (player) => `
                <tr class="${rowBorder}">
                  <td class="py-1.5 pr-2">${escapeHtml(player.player_name)} <span class="text-xs text-zinc-500">· ${escapeHtml(player.team_name)}</span></td>
                  <td class="py-1.5 px-2 text-right tabular-nums">${player.batting_points}</td>
                  <td class="py-1.5 px-2 text-right tabular-nums">${player.bowling_points}</td>
                  <td class="py-1.5 pl-2 text-right font-semibold tabular-nums">${player.total_points}</td>
                </tr>`,
                )
                .join("")}</tbody>
            </table></div>
          </div>`,
          )
          .join("")}
      </div>
    </details>`;
}

function editPanel() {
  return `
    <form id="series-edit-form" class="mt-4 rounded-xl border border-primary-500/30 bg-primary-500/5 p-4">
      <div class="grid gap-3 sm:grid-cols-2">
        <div class="sm:col-span-2">
          <label for="edit-name" class="block text-sm font-medium">Series name</label>
          <input id="edit-name" required maxlength="120" value="${escapeHtml(series.name)}"
            class="mt-1 min-h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" />
        </div>
        <div>
          <label for="edit-planned" class="block text-sm font-medium">Planned matches</label>
          <input id="edit-planned" type="number" min="${series.matches_played}" max="1000" value="${series.planned_matches}"
            class="mt-1 min-h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" />
          <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Cannot drop below ${series.matches_played} completed match${series.matches_played === 1 ? "" : "es"}.</p>
        </div>
        <div>
          <label for="edit-preset" class="block text-sm font-medium">Match type / rules preset</label>
          <select id="edit-preset" class="mt-1 min-h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950">
            <option value="">Mixed formats</option>
            ${presets
              .map(
                (preset) =>
                  `<option value="${escapeHtml(preset.key)}" ${series.preset === preset.key ? "selected" : ""}>${escapeHtml(preset.label)}</option>`,
              )
              .join("")}
          </select>
        </div>
        <div>
          <label for="edit-start" class="block text-sm font-medium">Start date</label>
          <input id="edit-start" type="date" value="${series.start_date || ""}"
            class="mt-1 min-h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" />
        </div>
        <div>
          <label for="edit-end" class="block text-sm font-medium">End date</label>
          <input id="edit-end" type="date" value="${series.end_date || ""}"
            class="mt-1 min-h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" />
        </div>
        ${["a", "b"]
          .map((side) => {
            const team = series[`team_${side}`] || { name: "", players: [] };
            return `
          <div class="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
            <label for="edit-team-${side}-name" class="block text-sm font-medium">Team ${side.toUpperCase()} name</label>
            <input id="edit-team-${side}-name" maxlength="80" value="${escapeHtml(team.name || "")}"
              class="mt-1 min-h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" />
            <label for="edit-team-${side}-players" class="mt-3 block text-sm font-medium">Players <span class="text-xs font-normal text-zinc-500">(comma or line separated)</span></label>
            <textarea id="edit-team-${side}-players" rows="4"
              class="mt-1 w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950">${escapeHtml((team.players || []).join("\n"))}</textarea>
          </div>`;
          })
          .join("")}
        <div class="sm:col-span-2">
          <label for="edit-notes" class="block text-sm font-medium">Notes</label>
          <textarea id="edit-notes" rows="2" maxlength="500"
            class="mt-1 w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950">${escapeHtml(series.notes || "")}</textarea>
        </div>
      </div>
      <div id="edit-feedback" class="mt-3" hidden></div>
      <div class="mt-3 flex flex-wrap gap-2">
        <button type="submit" class="inline-flex min-h-11 items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300">Save changes</button>
        <button type="button" id="edit-cancel" class="inline-flex min-h-11 items-center justify-center rounded-xl border border-zinc-300 px-4 text-sm font-semibold dark:border-zinc-700">Cancel</button>
      </div>
    </form>`;
}

function updateHeader() {
  document.title = `${series.name} — GullyScore`;
  const title = document.getElementById("series-title");
  const subtitle = document.getElementById("series-subtitle");
  if (title) title.textContent = series.name;
  if (subtitle) {
    subtitle.textContent = `${presetLabel(series.preset)} · ${series.matches_played} played · ${series.matches_remaining} remaining`;
  }
}

function normalizeSeries(value) {
  return {
    ...value,
    planned_matches: value.planned_matches ?? 0,
    matches_played: value.matches_played ?? 0,
    matches_remaining: value.matches_remaining ?? 0,
    match_count: value.match_count ?? (value.matches?.length || 0),
    teams: value.teams || [],
    standings: value.standings || [],
    mvp_leaderboard: value.mvp_leaderboard || [],
    match_fantasy: value.match_fantasy || [],
    recent_results: value.recent_results || [],
    batting_leaderboards: value.batting_leaderboards || {},
    bowling_leaderboards: value.bowling_leaderboards || {},
    awards: value.awards || {
      player_of_match: [],
      best_batter: { label: "Best Batter", winners: [], tied: false },
      best_bowler: { label: "Best Bowler", winners: [], tied: false },
      player_of_series: { label: "Player of the Series", winners: [], tied: false },
    },
  };
}

function render() {
  updateHeader();
  const newsletter = series.matches_played === 0;
  root.innerHTML = `
    <section class="${card}">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-primary-700 dark:text-primary-300">Series dashboard</p>
          <h2 class="mt-1 text-xl font-semibold">${escapeHtml(series.name)}</h2>
          <p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">${escapeHtml(presetLabel(series.preset))} · ${escapeHtml(dateRange(series.start_date, series.end_date))}</p>
          ${series.notes ? `<p class="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-300">${escapeHtml(series.notes)}</p>` : ""}
        </div>
        <div class="flex flex-wrap gap-2">
          <a href="/pages/matches.html?series=${series.id}" class="inline-flex min-h-11 items-center justify-center rounded-xl border border-zinc-300 px-4 text-sm font-semibold dark:border-zinc-700">Matches</a>
          <a href="/pages/match-type.html?series=${series.id}" class="inline-flex min-h-11 items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300">New match</a>
          <button type="button" id="edit-toggle" class="inline-flex min-h-11 items-center justify-center rounded-xl border border-zinc-300 px-4 text-sm font-semibold dark:border-zinc-700">${editing ? "Close editor" : "Edit series"}</button>
        </div>
      </div>
      <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        ${statCard("Played", series.matches_played, "completed matches")}
        ${statCard("Remaining", series.matches_remaining, `${series.match_count} linked in total`)}
        ${statCard("Teams", series.teams.length || "—", series.teams.length ? "selected roster" : "from matches")}
        ${statCard("MVP", series.awards?.player_of_series?.winners?.[0]?.player_name || "—", series.awards?.player_of_series?.value != null ? `${series.awards.player_of_series.value} fantasy pts` : "no completed match")}
      </div>
      ${teamChips()}
      ${editing ? editPanel() : ""}
    </section>

    ${standingsSection()}
    ${awardsSection()}
    ${mvpSection()}
    ${battingSection()}
    ${bowlingSection()}
    ${recentSection()}
    ${matchFantasySection()}
    ${newsletter ? `<p class="text-xs text-zinc-500 dark:text-zinc-400">No completed matches yet. Leaderboards and awards populate from completed series matches only.</p>` : ""}
  `;
  root.setAttribute("aria-busy", "false");
  bindControls();
}

async function saveSeries(event) {
  event.preventDefault();
  const feedback = document.getElementById("edit-feedback");
  const planned = Number(document.getElementById("edit-planned").value);
  if (!Number.isInteger(planned) || planned < series.matches_played) {
    setMessage(feedback, {
      type: "error",
      title: `Planned matches must be at least ${series.matches_played}.`,
    });
    return;
  }
  const players = (side) =>
    document
      .getElementById(`edit-team-${side}-players`)
      .value.split(/[\n,]+/)
      .map((player) => player.trim())
      .filter(Boolean);
  const teamA = {
    name: document.getElementById("edit-team-a-name").value.trim(),
    players: players("a"),
  };
  const teamB = {
    name: document.getElementById("edit-team-b-name").value.trim(),
    players: players("b"),
  };

  try {
    series = normalizeSeries(
      await apiPatch(`/api/series/${series.id}`, {
        name: document.getElementById("edit-name").value.trim(),
        planned_matches: planned,
        preset: document.getElementById("edit-preset").value || null,
        start_date: document.getElementById("edit-start").value || null,
        end_date: document.getElementById("edit-end").value || null,
        notes: document.getElementById("edit-notes").value.trim() || null,
        team_a: teamA,
        team_b: teamB,
      }),
    );
    editing = false;
    render();
  } catch (error) {
    setMessage(feedback, {
      type: "error",
      title: error.message,
      detail: describeDetails(error.details),
    });
  }
}

function bindControls() {
  document.getElementById("edit-toggle")?.addEventListener("click", () => {
    editing = !editing;
    render();
  });
  document.getElementById("edit-cancel")?.addEventListener("click", () => {
    editing = false;
    render();
  });
  document.getElementById("series-edit-form")?.addEventListener("submit", saveSeries);
}

async function loadPresets() {
  try {
    presets = (await fetchPresets()).presets || [];
  } catch {
    presets = [];
  }
}

async function init() {
  renderShell("matches");
  if (!seriesId) {
    root.innerHTML = `<p class="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-800 dark:text-amber-200">Choose a series from <a class="underline" href="/pages/matches.html">match history</a> or <a class="underline" href="/pages/series-new.html">create one</a>.</p>`;
    root.setAttribute("aria-busy", "false");
    return;
  }
  try {
    await loadPresets();
    series = normalizeSeries(await apiGet(`/api/series/${seriesId}`));
    render();
  } catch (error) {
    root.innerHTML = errorPanel(error.message);
    root.setAttribute("aria-busy", "false");
  }
}

init();
