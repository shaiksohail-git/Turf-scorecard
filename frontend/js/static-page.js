import { renderShell } from "../components/shell.js";

const params = new URLSearchParams(window.location.search);
const seriesId = params.get("series");
if (seriesId) {
  document.querySelectorAll('a[href^="/pages/setup-"]').forEach((link) => {
    const url = new URL(link.href);
    url.searchParams.set("series", seriesId);
    link.href = `${url.pathname}${url.search}`;
  });
}

renderShell(document.body.dataset.nav || "");
