import { apiGet, apiPost, ApiError } from "./api.js";
import { describeDetails, setMessage } from "./dom.js";
import { registerPwa } from "./pwa.js";

const form = document.getElementById("auth-form");
const feedback = document.getElementById("auth-feedback");
const submit = document.getElementById("auth-submit");
const switchButton = document.getElementById("auth-switch");
const registerFields = document.getElementById("register-fields");
const title = document.getElementById("auth-title");
const subtitle = document.getElementById("auth-subtitle");
const passwordHelp = document.getElementById("password-help");
let registering = false;
let registrationOpen = false;

function nextPath() {
  const target = new URLSearchParams(window.location.search).get("next");
  return target && target.startsWith("/") && !target.startsWith("//") ? target : "/";
}

function renderMode() {
  registerFields.hidden = !registering;
  passwordHelp.hidden = !registering;
  title.textContent = registering ? "Create your account" : "Sign in to score";
  subtitle.textContent = registering
    ? "The first account owns this deployment. Registration is closed afterwards unless enabled."
    : "Your matches and series are private to your account.";
  submit.textContent = registering ? "Create account" : "Sign in";
  switchButton.hidden = registering ? !registrationOpen : !registrationOpen;
  switchButton.textContent = registering ? "I already have an account" : "Create the first account";
}

async function loadSession() {
  try {
    const session = await apiGet("/api/auth/session");
    registrationOpen = Boolean(session.registration_open);
    document.getElementById("local-continue").hidden = Boolean(session.auth_required);
    if (!session.auth_required) {
      window.location.replace(nextPath());
      return;
    }
    if (session.authenticated) {
      window.location.replace(nextPath());
      return;
    }
    registering = registrationOpen;
    renderMode();
  } catch (error) {
    setMessage(feedback, { type: "error", title: error.message });
  }
}

async function submitAuth(event) {
  event.preventDefault();
  if (submit.disabled) return;
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  if (!email || !password) {
    setMessage(feedback, { type: "error", title: "Enter your email and password." });
    return;
  }

  submit.disabled = true;
  submit.textContent = registering ? "Creating…" : "Signing in…";
  setMessage(feedback, null);
  try {
    if (registering) {
      await apiPost("/api/auth/register", {
        display_name: document.getElementById("display-name").value.trim(),
        email,
        password,
      });
    } else {
      await apiPost("/api/auth/login", { email, password });
    }
    window.location.assign(nextPath());
  } catch (error) {
    setMessage(feedback, {
      type: "error",
      title: error instanceof ApiError && error.status === 401 ? "Email or password is incorrect." : error.message,
      detail: describeDetails(error.details),
    });
  } finally {
    submit.disabled = false;
    submit.textContent = registering ? "Create account" : "Sign in";
  }
}

switchButton.addEventListener("click", () => {
  registering = !registering;
  renderMode();
});
form.addEventListener("submit", submitAuth);
registerPwa();
loadSession();
