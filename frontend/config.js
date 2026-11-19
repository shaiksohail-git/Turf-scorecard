/**
 * Runtime API origin for split deployments (for example Vercel frontend +
 * Flask/Render API). Leave empty when Flask serves the frontend same-origin.
 * Set it to the backend origin before deploying the static frontend, e.g.
 * window.GULLY_API_BASE = "https://gullyscore-api.onrender.com";
 */
window.GULLY_API_BASE = "";
