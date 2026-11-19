import { apiPost, fetchPresets } from "./api.js";
import { describeDetails, escapeHtml, setMessage } from "./dom.js";
import { renderShell } from "../components/shell.js";

const form = document.getElementById("series-form");
const feedback = document.getElementById("series-feedback");
const submitButton = document.getElementById("series-submit");
let submitting = false;

async function loadPresets() {
  try {
    const data = await fetchPresets();
    const select = document.getElementById("series-preset");
    select.innerHTML =
      `<option value="">Mixed formats</option>` +
      data.presets
        .map((preset) => `<option value="${escapeHtml(preset.key)}">${escapeHtml(preset.label)}</option>`)
        .join("");
  } catch {
    /* the series can still be created without a default format */
  }
}

function playersFrom(id) {
  return [...new Set(
    document
      .getElementById(id)
      .value.split(/[\n,]+/)
      .map((player) => player.trim())
      .filter(Boolean),
  )];
}

async function submit(event) {
  event.preventDefault();
  if (submitting) return;
  setMessage(feedback, null);

  const name = document.getElementById("series-name").value.trim();
  const start = document.getElementById("series-start").value;
  const end = document.getElementById("series-end").value;
  const planned = Number(document.getElementById("series-planned").value || 0);
  const teamAName = document.getElementById("series-team-a-name").value.trim();
  const teamBName = document.getElementById("series-team-b-name").value.trim();
  const teamAPlayers = playersFrom("series-team-a-players");
  const teamBPlayers = playersFrom("series-team-b-players");

  if (!name) {
    setMessage(feedback, { type: "error", title: "A series name is required." });
    return;
  }
  if (start && end && end < start) {
    setMessage(feedback, { type: "error", title: "The end date cannot be before the start date." });
    return;
  }
  if (!Number.isInteger(planned) || planned < 0) {
    setMessage(feedback, { type: "error", title: "Planned matches must be a whole number of zero or more." });
    return;
  }
  if ((teamAName || teamBName) && (!teamAName || !teamBName)) {
    setMessage(feedback, { type: "error", title: "Choose both teams, or leave both blank." });
    return;
  }
  if (!teamAName && (teamAPlayers.length || teamBPlayers.length)) {
    setMessage(feedback, { type: "error", title: "Add team names before adding players." });
    return;
  }
  if (teamAName && (!teamAPlayers.length || !teamBPlayers.length)) {
    setMessage(feedback, { type: "error", title: "Add at least one player to each selected team." });
    return;
  }

  submitting = true;
  submitButton.disabled = true;
  submitButton.setAttribute("aria-busy", "true");
  submitButton.textContent = "Creating…";

  try {
    const preset = document.getElementById("series-preset").value || null;
    const series = await apiPost("/api/series", {
      name,
      preset,
      format: preset,
      planned_matches: planned,
      start_date: start || null,
      end_date: end || null,
      notes: document.getElementById("series-notes").value.trim() || null,
      team_a: teamAName ? { name: teamAName, players: teamAPlayers } : null,
      team_b: teamBName ? { name: teamBName, players: teamBPlayers } : null,
    });
    setMessage(feedback, {
      type: "success",
      title: `“${series.name}” created`,
      detail: "Open the dashboard to edit the series and follow its leaderboards.",
    });
    form.reset();
    const link = document.createElement("a");
    link.href = `/pages/series.html?id=${series.id}`;
    link.className =
      "mt-3 inline-flex min-h-11 items-center justify-center rounded-xl bg-primary-400 px-4 text-sm font-bold text-emerald-950 hover:bg-primary-300";
    link.textContent = "View series dashboard";
    feedback.appendChild(link);
  } catch (error) {
    setMessage(feedback, {
      type: "error",
      title: error.message,
      detail: describeDetails(error.details),
    });
  } finally {
    submitting = false;
    submitButton.disabled = false;
    submitButton.removeAttribute("aria-busy");
    submitButton.textContent = "Create series";
  }
}

renderShell("matches");
loadPresets();
form.addEventListener("submit", submit);
