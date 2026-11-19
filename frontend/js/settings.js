import { apiGet, apiPatch, apiPost, fetchHealth } from "./api.js";
import { describeDetails, escapeHtml, setMessage } from "./dom.js";
import { saveScorerName } from "./prefs.js";
import { renderShell } from "../components/shell.js";

const feedback = document.getElementById("profile-feedback");
const nameInput = document.getElementById("display-name");
const saveButton = document.getElementById("save-profile");
let saving = false;

async function loadProfile() {
  try {
    const user = await apiGet("/api/users/me");
    nameInput.value = user.display_name;
    saveScorerName(user.display_name);
  } catch (error) {
    setMessage(feedback, { type: "error", title: error.message });
  }
}

async function saveProfile(event) {
  event.preventDefault();
  if (saving) return;
  const displayName = nameInput.value.trim();
  if (displayName.length < 2) {
    setMessage(feedback, { type: "error", title: "Use at least 2 characters for the display name." });
    return;
  }

  saving = true;
  saveButton.disabled = true;
  saveButton.setAttribute("aria-busy", "true");
  saveButton.textContent = "Saving…";
  setMessage(feedback, null);

  try {
    const user = await apiPatch("/api/users/me", { display_name: displayName });
    nameInput.value = user.display_name;
    saveScorerName(user.display_name);
    setMessage(feedback, {
      type: "success",
      title: "Profile saved",
      detail: "New scoring actions will use this name in the audit trail.",
    });
  } catch (error) {
    setMessage(feedback, {
      type: "error",
      title: error.message,
      detail: describeDetails(error.details),
    });
  } finally {
    saving = false;
    saveButton.disabled = false;
    saveButton.removeAttribute("aria-busy");
    saveButton.textContent = "Save profile";
  }
}

async function checkHealth() {
  const line = document.getElementById("health-status");
  line.textContent = "Checking the API…";
  try {
    const health = await fetchHealth();
    line.innerHTML = `
      <span class="font-semibold text-primary-700 dark:text-primary-300">API online</span>
      <span aria-hidden="true"> · </span> v${escapeHtml(health.version)}
      <span aria-hidden="true"> · </span> database ${health.database ? "connected" : "unavailable"}`;
  } catch (error) {
    line.innerHTML = `<span class="font-semibold text-red-700 dark:text-red-300">API offline</span> · ${escapeHtml(error.message)}`;
  }
}

async function loadSession() {
  const line = document.getElementById("auth-status");
  const logout = document.getElementById("logout-button");
  try {
    const session = await apiGet("/api/auth/session");
    if (!session.auth_required) {
      line.textContent = "Local development mode — no sign-in required.";
      logout.hidden = true;
      return;
    }
    line.textContent = session.authenticated
      ? `Signed in as ${session.user.display_name}${session.user.email ? ` (${session.user.email})` : ""}.`
      : "Not signed in.";
    logout.hidden = !session.authenticated;
  } catch (error) {
    line.textContent = error.message;
  }
}

async function logout() {
  try {
    await apiPost("/api/auth/logout");
    window.location.assign("/pages/login.html");
  } catch (error) {
    setMessage(feedback, { type: "error", title: error.message });
  }
}

async function init() {
  renderShell("settings");
  document.getElementById("profile-form").addEventListener("submit", saveProfile);
  document.getElementById("refresh-health").addEventListener("click", checkHealth);
  document.getElementById("logout-button").addEventListener("click", logout);
  await loadSession();
  await loadProfile();
  await checkHealth();
}

init();
