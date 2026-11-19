import { apiGet } from "./api.js";
import { renderShell } from "../components/shell.js";
import { emptyState, errorPanel, matchCard } from "../components/ui.js";

function setup() {
  renderShell("home");
  const today = document.getElementById("today");
  if (today) {
    today.textContent = new Date().toLocaleDateString(undefined, {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
  }
  loadMatches();
}

async function loadMatches() {
  await Promise.all([loadOngoing(), loadRecent()]);
}

async function loadOngoing() {
  const container = document.getElementById("ongoing");
  if (!container) return;
  try {
    const matches = await apiGet("/api/matches?status=live&limit=10");
    container.innerHTML = matches.length
      ? matches.map(matchCard).join("")
      : emptyState({
          title: "No match in progress",
          detail: "Start a new match and the live scoreboard will appear here.",
          href: "/pages/match-type.html",
          label: "New match",
        });
  } catch (error) {
    container.innerHTML = errorPanel(error.message);
  } finally {
    container.setAttribute("aria-busy", "false");
  }
}

async function loadRecent() {
  const container = document.getElementById("recent");
  if (!container) return;
  try {
    const matches = await apiGet("/api/matches?status=completed&limit=5");
    container.innerHTML = matches.length
      ? matches.map(matchCard).join("")
      : emptyState({
          title: "No completed matches yet",
          detail: "Finished games and their results will be listed here.",
          href: "/pages/matches.html",
          label: "Match history",
        });
  } catch (error) {
    container.innerHTML = errorPanel(error.message);
  } finally {
    container.setAttribute("aria-busy", "false");
  }
}

setup();
