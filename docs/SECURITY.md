# GullyScore security

This checklist covers the Phase 5 security work. It is intentionally small and
single-scorekeeper focused; it is not a claim of a formal security audit.

## Implemented controls

- **Authentication**: optional Flask signed-session auth, enabled with
  `AUTH_REQUIRED=true`. The first account bootstraps a deployment; later
  registration is closed unless `ALLOW_REGISTRATION=true`.
- **Password storage**: Werkzeug salted `scrypt`/PBKDF2 hashes. Plaintext
  passwords are never stored, logged or returned.
- **Session cookies**: HttpOnly, SameSite configurable, Secure when enabled;
  seven-day lifetime by default.
- **CSRF**: every authenticated API mutation requires `X-CSRF-Token` matching
  the signed-session token. The token is also mirrored in a non-HttpOnly
  `gully_csrf` cookie for the browser client. Same-origin checks are enforced by
  the browser client; CORS is restricted in production.
- **Authorization**: matches and series are scoped to `owner_id`; cross-owner
  reads/writes return `403` when auth is enabled. Lists filter by owner.
- **Validation**: typed JSON bodies, bounded integers, enum checks, maximum
  request size (`MAX_CONTENT_LENGTH=1 MiB`), password length limits and
  normalized email addresses. The scoring engine validates every delivery.
- **Rate limiting**: fixed-window limits for auth, scoring and general API
  traffic. `Retry-After` is returned on `429`. It is process-local, so use one
  worker or a shared limiter when scaling.
- **Audit logs**: `audit_logs` records registration, sign-in, failed sign-in,
  logout and password changes with actor, user id, IP/user-agent (when trusted
  proxy headers are enabled) and JSON details. Match actions continue to use the
  append-only `match_events` trail.
- **Transport**: `SESSION_COOKIE_SECURE=true` enables Secure cookies and an HSTS
  header. TLS is expected at the host/reverse proxy.
- **Headers**: CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy`, and `Cache-Control: no-store` for
  API responses.
- **Offline safety**: deliveries are written to a local queue before sending;
  the server enforces `(innings_id, client_event_id)` uniqueness, so retries and
  interrupted syncs are exactly-once. Undo and retirement changes remain
  online-only.
- **Backups**: `scripts/backup.sh` produces custom-format PostgreSQL dumps with
  restricted permissions and retention. Test restores separately.

## Production checklist

- [ ] `AUTH_REQUIRED=true` and a strong, unique `GULLY_SECRET_KEY`.
- [ ] First account created, then `ALLOW_REGISTRATION=false`.
- [ ] PostgreSQL reachable only over TLS / a private network; migrations applied.
- [ ] `SESSION_COOKIE_SECURE=true`; HTTPS redirect enabled.
- [ ] `CORS_ORIGINS` contains exact frontend origins, not `*`.
- [ ] `TRUST_PROXY=true` only behind a trusted proxy that overwrites forwarding
      headers.
- [ ] One Gunicorn worker unless the rate limiter is moved to shared storage.
- [ ] Backups scheduled, encrypted and restore-tested.
- [ ] `scripts/smoke_test.sh` passes on the live origin.
- [ ] Browser sign-in, cross-account `403`, CSRF rejection and offline replay
      checks completed.

## Known limitations

- SQLite is used by the automated test suite; PostgreSQL is the supported
  production database. Run migrations and a smoke test on PostgreSQL before
  relying on a production deployment.
- The rate limiter and sessions are process-local. Multi-instance deployments
  need a shared limiter and a shared session/auth strategy.
- The service worker may cache authenticated GET responses on the local device
  for offline scorekeeping. Use a dedicated device/browser profile for scoring
  and clear site data when handing the device on.
- Fielding/captaincy fantasy and multi-device realtime sync are out of scope.
