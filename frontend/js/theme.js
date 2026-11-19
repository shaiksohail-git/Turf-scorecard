/** Dark-by-default theme handling with a remembered preference. */

const STORAGE_KEY = "gully-theme";
const THEME_COLORS = { dark: "#07110c", light: "#f6f8f7" };

export function storedTheme() {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "dark";
  } catch {
    return "dark";
  }
}

export function currentTheme() {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function applyTheme(theme) {
  const dark = theme !== "light";
  document.documentElement.classList.toggle("dark", dark);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", dark ? THEME_COLORS.dark : THEME_COLORS.light);
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.setAttribute("aria-pressed", String(dark));
    button.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    button.title = dark ? "Switch to light theme" : "Switch to dark theme";
  });
  document.querySelectorAll("[data-theme-option]").forEach((button) => {
    const selected = button.dataset.themeOption === (dark ? "dark" : "light");
    button.setAttribute("aria-pressed", String(selected));
  });
}

function setTheme(theme) {
  applyTheme(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* private mode: the toggle still works for this page load */
  }
}

export function initThemeToggle() {
  const toggles = document.querySelectorAll("[data-theme-toggle]");
  if (!toggles.length) return;

  applyTheme(storedTheme());

  toggles.forEach((button) => {
    button.addEventListener("click", () => {
      setTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  });

  document.querySelectorAll("[data-theme-option]").forEach((button) => {
    button.addEventListener("click", () => setTheme(button.dataset.themeOption));
  });
}
