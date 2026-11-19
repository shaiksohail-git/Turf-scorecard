# GullyScore deployment

GullyScore has two deployable pieces:

1. **Flask API + static frontend** — PostgreSQL, Gunicorn, the REST API and the
   same-origin HTML/CSS/JS. This is the simplest and recommended deployment.
2. **Static frontend on Vercel** — only when the API is hosted elsewhere. Set
   `window.GULLY_API_BASE` in `frontend/config.js` to the API origin and allow
   that origin in `CORS_ORIGINS`.

The repository does not include credentials, a production database or a live
domain. A deployment is only verified after the smoke test below has been run
against the actual URL.

## 1. Database

Create a PostgreSQL 13+ database and a least-privilege application user. Apply
every migration from the repository root or the backend directory:

```bash
export DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/gullyscore"
cd backend
flask --app wsgi db upgrade
flask --app wsgi db check
```

`db check` must print `No new upgrade operations detected.` before starting the
web process. Do not use `db.create_all()` in production; migrations are the
source of truth.

### Backups

Run `scripts/backup.sh` from a scheduler with `DATABASE_URL` set. It writes a
custom-format `pg_dump` with permissions `0600` and deletes dumps older than 30
days. Store backups outside the application host, encrypt them at rest and test
a restore into a separate database regularly:

```bash
pg_restore --clean --if-exists --no-owner -d "$RESTORE_DATABASE_URL" backup.dump
```

## 2. Backend

### Render

`render.yaml` defines a Python web service and a managed PostgreSQL database.
Before deploying, replace `YOUR-FRONTEND.vercel.app` in `CORS_ORIGINS` with the
real frontend origin. Render supplies `DATABASE_URL` from the database. Set a
strong `GULLY_SECRET_KEY`; the blueprint generates one.

The start command deliberately uses **one worker with four threads**. The
rate limiter is process-local, and a single scorekeeper workload does not need
multiple web workers. If you scale to multiple processes/instances, replace the
limiter with a shared store (for example Redis) before relying on its limits.

### Docker / any container host

```bash
docker build -t gullyscore .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql+psycopg://..." \
  -e GULLY_SECRET_KEY="..." \
  -e AUTH_REQUIRED=true \
  -e ALLOW_REGISTRATION=false \
  -e SESSION_COOKIE_SECURE=true \
  -e TRUST_PROXY=true \
  -e CORS_ORIGINS="https://your-frontend.example" \
  gullyscore
```

The container runs Gunicorn from `backend/wsgi.py`. Run migrations as a release
step before the new process receives traffic.

### Required environment

| Variable | Production value |
| --- | --- |
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL |
| `GULLY_SECRET_KEY` | long random secret, never committed |
| `AUTH_REQUIRED` | `true` |
| `ALLOW_REGISTRATION` | `false` after the first account is created |
| `SESSION_COOKIE_SECURE` | `true` |
| `SESSION_COOKIE_SAMESITE` | `Lax` for same-origin, `None` for cross-site cookies |
| `TRUST_PROXY` | `true` only behind a trusted reverse proxy |
| `CORS_ORIGINS` | comma-separated exact frontend origins |
| `PORT` | injected by Render/Render-like hosts |

## 3. Frontend on Vercel

The static site is in `frontend/`. `vercel.json` publishes that directory and
sets no-cache headers for the service worker. Before deploying:

1. Set `window.GULLY_API_BASE` in `frontend/config.js` to the public API origin
   (no trailing slash).
2. Add the Vercel origin to `CORS_ORIGINS`.
3. If cookies are cross-site, set `SESSION_COOKIE_SAMESITE=None` and
   `SESSION_COOKIE_SECURE=true`; HTTPS is mandatory.
4. Create the first account with `ALLOW_REGISTRATION=true`, then turn it off.

For a same-origin deployment, leave `GULLY_API_BASE` empty and serve the
frontend from Flask. This avoids cross-site cookies and CORS entirely and is the
recommended production shape.

## 4. Custom domain and HTTPS

Terminate TLS at the host or reverse proxy and forward `X-Forwarded-Proto` and
`X-Forwarded-For`. Set `TRUST_PROXY=true` only when those headers are supplied
by a trusted proxy. Point the domain at the service, then update
`CORS_ORIGINS`, `window.GULLY_API_BASE` and the OAuth/callback origins if auth
providers are added later. Keep HTTP redirected to HTTPS.

## 5. Smoke test

After migrations and a deploy, run:

```bash
BASE_URL=https://your-api.example \
  ./scripts/smoke_test.sh
```

The script checks health (including the database), rule presets, the PWA
manifest and the match-list authorization response. It deliberately accepts
`401` for the match list because a production deployment should require auth.

Manual production checks:

- Sign in, create a match, score several balls, undo one, and open the
  scorecard.
- Install the PWA, go offline, score a ball, confirm the offline banner, then
  reconnect and confirm exactly one delivery was recorded.
- Sign out and verify protected pages redirect to the login page.
- Verify the browser reports no console errors and that `/sw.js` and
  `/manifest.webmanifest` are served with the expected content types.
