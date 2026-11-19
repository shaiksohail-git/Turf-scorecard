# GullyScore

Rule-aware, ball-by-ball cricket scoring for 6-over turf games and full T20
matches. One configurable scoring engine, per-match rule snapshots, and an
append-only delivery log so corrections never rewrite history.

- **Backend:** Python 3.11+, Flask, SQLAlchemy, Alembic (Flask-Migrate), PostgreSQL
- **Frontend:** static HTML, compiled Tailwind CSS, ES modules — no framework
- **Tests:** 163 pytest tests covering rules, scoring, extras, wickets, API lifecycle, normalized schema, stats, solo batting, retirements, fantasy, series management, authentication, authorization, pagination and security headers

## Phase 5 scope

Phase 5 makes the application deployable and resilient without rebuilding the
scoring core. The event-sourced engine and all Phase 2–4 read models remain the
source of truth.

| Area | Delivered |
| --- | --- |
| Testing | 163 automated tests for T20/custom/turf scoring, extras, free hits, wickets, solo batting, retirements, strike rotation, innings transitions, DLS-free run chases, results, fantasy, series boards, undo/corrections, auth, CSRF, ownership, rate limits, pagination and headers |
| Offline PWA | Manifest, installable app shell, versioned service worker with automatic update reload, offline indicator, durable localStorage delivery queue, exactly-once retry via `client_event_id`, a rejected-delivery recovery list, and online-only conflict-sensitive undo/retirements |
| Reliability | Collapsible desktop sidebar with remembered state and a content offset; over-limit bowlers are disabled in the scoring pad; rejected deliveries are archived instead of blocking later balls, with pending/rejected counts and a discard action on the live page |
| Performance | Composite indexes for match history/events, paginated `/api/matches` with metadata, load-more history UI, one GET per idle scoring refresh, and a cache-first static shell |
| Security | Optional signed-session auth, Werkzeug password hashing, owner-scoped matches/series, CSRF protection, validation, fixed-window rate limits, security headers, HSTS when TLS is enabled and an audit-log table |
| Deployment | Gunicorn Procfile, Dockerfile, Render blueprint, Vercel static config, CI workflow, backup script and production smoke test |
| Documentation | [Deployment](docs/DEPLOYMENT.md), [security checklist](docs/SECURITY.md), expanded [API reference](docs/API.md) and environment template |

Production authentication is opt-in with `AUTH_REQUIRED=true` so local scoring
and the automated suite remain usable without a login. See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the deployment sequence and the
live smoke-test command.

## Phase 4 scope

Phase 4 adds series management and derived series competition views. A series
stores its planned length and optional two-team roster, and can be edited
without touching linked matches, their frozen rules or historical results.

| Area | Delivered |
| --- | --- |
| Series creation | Name, match type/rules preset, teams, players, planned matches, dates and notes |
| Series editing | Rename, roster/rules metadata, dates and planned length; never below completed matches and never deletes a match |
| Dashboard | Teams, played/remaining, standings, wins/losses, MVP, recent results and match-wise fantasy |
| Batting boards | Runs, highest score, average, strike rate, fours, sixes, fifties and centuries |
| Bowling boards | Wickets, economy, best figures, average, strike rate, maidens and dot balls |
| Fantasy | Cumulative, batting and bowling points from the per-match ledger; fielding and captaincy excluded |
| Awards | Player of the Match, Best Batter, Best Bowler and Player of the Series with tied winners and deterministic ordering |
| Qualification | Minimum innings/balls/wickets thresholds for rate-based boards |
| Migrations | Fourth Alembic revision adds `planned_matches` and the selected team/player columns, backfilling the plan from existing links |
| Tests | Phase 4 scenarios cover creation/editing, length boundaries, preservation, every board, fantasy, tie awards, thresholds and recalculation after undo |

Series figures are a projection over completed matches, rebuilt on every read
from deliveries, retirements and the fantasy ledger. No series totals are stored
beside match totals, so an undo or correction cannot leave a stale or duplicated
series result.

## Phase 3 scope

Phase 3 extends the existing engine with solo batting, retirement management,
advanced scorecards, player/team statistics and a configurable fantasy-points
ledger. Historical scorecards and results are rebuilt from events, so a
correction recalculates statistics instead of leaving stale totals.

| Area | Delivered |
| --- | --- |
| Solo batting | Auto-detects the last batter, disables rotation, keeps runs/balls/boundaries/SR, and ends only on dismissal or the scheduled limit |
| Retirements | Retired not out, retired out and retired hurt with reason, timestamp, replacement, return-to-batting, eligibility rules and audit events |
| Scorecard | Batting, bowling, extras breakdown, fall of wickets, partnerships, retirement notation and ball-by-ball commentary |
| Player stats | Runs, highest score, average, strike rate, fours/sixes, wickets, bowling average, economy, best bowling and fantasy points |
| Team stats | Matches, wins, losses, ties, highest/lowest score and win percentage |
| Fantasy | Runs, boundaries, milestones, ducks, wickets, bowled/LBW, maidens, 3/4/5-wicket hauls and configurable strike-rate/economy; T20 and short-format presets; itemized `fantasy_points` ledger |
| Migrations | Third Alembic revision adds retirements, the fantasy ledger, `matches.fantasy_config` and extended player-stat columns |
| Tests | 15 Phase 3 scenarios covering solo batting, every retirement path, advanced cards, stats and fantasy rebuilds |

## Phase 2 scope

Phase 1 delivered the foundation: a normalized PostgreSQL schema with migrations,
the rule and scoring engines, the REST API and every initial screen. Phase 2
hardens the scoring core: transactional writes, exactly-once delivery recording,
integer legal-ball accounting, all three presets, the full two-innings workflow,
match results, undo/correction and automated scoring tests.

| Area | Delivered |
| --- | --- |
| Database | 12 normalized tables, FKs, timestamps, indexes, CHECK constraints, two Alembic revisions |
| Scoring | Presets, frozen rule snapshots, event-sourced deliveries, replay, void-based undo, audit trail |
| Match workflow | Two innings with automatic target, win by runs/wickets, ties, reopening a finished chase on undo |
| Guarantees | One transaction per command, exactly-once deliveries, per-ball validation, integer legal balls |
| API | REST endpoints for rules, matches, innings, deliveries, series, users, stats and match events |
| UI | Responsive dark-first shell (desktop sidebar, mobile bottom nav), theme toggle, scoring pad, scorecard, stats, settings |
| Tests | 127 pytest tests run against SQLite; `flask db check` reports no drift |

## Project layout

```
frontend/                     static site served by Flask (same origin as the API)
  index.html                  Home: ongoing matches, recent results, New Match
  pages/matches.html          Match history with status filters and series view
  pages/match-type.html       Format selection (T20 / Custom Match / Custom Turf)
  pages/setup-t20.html        Full T20 setup
  pages/setup-custom.html     Custom Match setup
  pages/setup-turf.html       Custom Turf setup
  pages/series-new.html       Series creation with roster and planned length
  pages/series.html           Series dashboard, boards, fantasy and awards
  pages/live.html             Live scoring pad with offline queue and recovery
  pages/scorecard.html        Full batting/bowling scorecard
  pages/stats.html            Totals and leaderboards
  pages/settings.html         Appearance, scorer profile, system status
  pages/login.html            Optional sign-in and first-account bootstrap
  sw.js                       Versioned app-shell service worker
  components/shell.js         Sidebar/topbar/bottom nav, theme toggles, collapsible sidebar
  components/ui.js            Reusable cards, badges, empty and error states
  css/tailwind.css            Tailwind source
  css/app.css                 Compiled stylesheet (committed)
  js/                         API client, DOM helpers, theme/prefs, page scripts
backend/
  config.py                   environment-driven configuration
  wsgi.py                     app entry point
  app/
    models/                   User, Team, Player, Match, MatchTeam, MatchRules,
                              Innings, Delivery, Series, SeriesMatch, MatchEvent,
                              PlayerMatchStatistics, Retirement, FantasyPoint, AuditLog
    services/                 rules, scoring, innings, match, statistics, scorecard,
                              series, users, stats
    routes/                   health, rules, matches, scoring, series, users, stats, auth
    utils/                    serializers and request helpers
  migrations/                 Alembic environment + revisions
database/schema.sql           PostgreSQL reference DDL (mirrors the head revision)
docs/                         PRD, TRD, architecture decisions, API reference
tests/                        pytest suite
```

## Requirements

- Python 3.11+ (developed on 3.13)
- PostgreSQL 13+
- Node 18+ only if you rebuild the CSS (`frontend/css/app.css` is committed)

## Setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env          # then set DATABASE_URL and GULLY_SECRET_KEY
```

Create the database and apply all Alembic migrations:

```bash
createdb gullyscore
cd backend
flask --app wsgi db upgrade
flask --app wsgi db check     # expect: No new upgrade operations detected
```

Run the app (API and frontend on the same origin):

```bash
cd backend
python wsgi.py
# or: flask --app wsgi run --debug
```

Open <http://127.0.0.1:5000>. Health check: <http://127.0.0.1:5000/api/health>.

### Running without a local PostgreSQL server

PostgreSQL is the supported database. For a quick UI/API check on a machine
without one, point `DATABASE_URL` at a local SQLite file and run the same
migrations (the schema only uses portable types):

```bash
cd backend
DATABASE_URL="sqlite+pysqlite:///./dev.db" flask --app wsgi db upgrade
DATABASE_URL="sqlite+pysqlite:///./dev.db" python wsgi.py
```

Flask-SQLAlchemy resolves that relative SQLite path inside `backend/instance/`.

## Screens

Every screen is a standalone HTML document with an ES module page script; there
is no client-side router and no framework.

| Screen | Route | Behaviour |
| --- | --- | --- |
| Home | `/` | Ongoing matches, last five results, New Match call to action, link to history |
| Match history | `/pages/matches.html` | Filter All / Live / Completed / Drafts, optional `?series=` view |
| Match type | `/pages/match-type.html` | Choose Full T20, Custom Match or Custom Turf |
| Setup | `/pages/setup-turf.html` etc. | Teams, squads in batting order, toss, editable rules, creates and starts the match |
| Series creation | `/pages/series-new.html` | Name, match type/preset, teams, players, planned matches, dates and notes |
| Series dashboard | `/pages/series.html?id=1` | Editable details/length, standings, MVP, every batting/bowling board, rewards and recent results |
| Live scoring | `/pages/live.html?match=1` | Scoreboard, solo mode, striker/non-striker, over-limit-safe bowler selection, run pad, extras, wicket, undo, free hit, retire/return, offline queue and rejected-ball recovery |
| Scorecard | `/pages/scorecard.html?match=1` | Batting, bowling, extras, fall of wickets, partnerships, retirements and ball-by-ball commentary |
| Stats | `/pages/stats.html` | Totals, run/wicket/fantasy leaderboards, full player table and team win/loss table |
| Settings | `/pages/settings.html` | Dark/light preference, scorer display name, API health |

Design: dark by default with a remembered light theme, accent `#52E4A0`,
mobile-first spacing, bottom navigation below `lg`, a collapsible fixed sidebar
at `lg` and up, minimum 44px touch targets, visible focus rings and skip links.
The sidebar offset is applied to the page body, so the main content never sits
under it; its open/closed state is remembered in local storage.

## Reliability and offline behaviour

- A completed ball is written to `gully-score-queue-v1` before the request is
  sent, so a dropped connection does not lose it. The server's
  `(innings_id, client_event_id)` constraint makes retries idempotent.
- `409` and `422` responses are moved to `gully-score-failed-v1` instead of
  staying at the head of the queue. This keeps one invalid ball from blocking
  every later ball. The live page reports the count and can discard the local
  recovery entries.
- Network errors and `401` stop the current sync without discarding the queue;
  the next online event or background sync retry resumes it.
- Only one sync runs at a time. Undo and retirement changes remain online-only
  because they need the current innings state.
- The scoring pad disables bowlers who have reached `max_overs_per_bowler` and
  automatically selects an eligible bowler when the previous over ended on a
  bowler's limit.
- The service worker bumps its cache version with each shell change and reloads
  once when a new worker takes control, so an open tab does not stay on stale
  JavaScript or CSS.

## Database

| Table | Purpose |
| --- | --- |
| `users` | Match owner and scorer profile, including optional password hash and last login |
| `audit_logs` | Security events (registration, login, logout, password changes) with actor/IP/user-agent |
| `teams`, `players` | Squads created per match, with batting order and role |
| `matches` | Lifecycle, frozen `rules` JSON snapshot, toss, result, revision |
| `match_teams` | Per-match participation: side, toss winner, who bats first |
| `match_rules` | Normalized copy of the frozen snapshot for querying/reporting |
| `innings` | Two innings per match, aggregates cached from events |
| `deliveries` | Append-only ball log; undo marks a row void |
| `match_events` | Audit trail (created, started, delivery recorded/voided) |
| `series`, `series_matches` | Grouping, owner, planned length, selected teams/players and order of matches inside a series |
| `player_match_statistics` | Per-player, per-match projection rebuilt from deliveries, including highest score, not-outs, best bowling and fantasy points |
| `retirements` | Innings events anchored to the delivery count, with replacement, reason, timestamp and return |
| `fantasy_points` | Itemized, rebuildable ledger with one unique source key per award |

`matches.team_a_id`, `team_b_id` and `series_id` stay as fast lookup columns
while `match_teams` and `series_matches` hold the normalized rows; both are
written in the same transaction. See [docs/architecture.md](docs/architecture.md)
(ADR-12 and ADR-13) for why.

## API summary

Full reference with payloads and error codes: [docs/API.md](docs/API.md).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | App version, database status, server time |
| GET | `/api/rules/presets` | Three presets with resolved rules |
| POST | `/api/rules/validate` | Resolve/validate a preset plus overrides |
| POST | `/api/matches` | Create teams, players and a draft match |
| GET | `/api/matches` | Paginated summaries (`page`, `per_page`, `status`, `series_id`; legacy `limit` supported) |
| GET | `/api/matches/{id}` | Full detail incl. squads, rules, match teams |
| POST | `/api/matches/{id}/start` | Create both innings and go live |
| GET | `/api/matches/{id}/scorecard` | Advanced scorecard for every innings |
| GET | `/api/matches/{id}/fantasy` | Fantasy configuration, totals and itemized ledger |
| GET | `/api/matches/{id}/events` | Audit timeline, newest first |
| GET | `/api/innings/{id}` | Live innings state |
| GET | `/api/innings/{id}/deliveries` | Delivery log (`include_voided`) |
| POST | `/api/innings/{id}/deliveries` | Record a ball (idempotent, optional revision check) |
| POST | `/api/innings/{id}/deliveries/undo` | Void the last ball and replay |
| GET/POST | `/api/innings/{id}/retirements` | Retirement history and recording |
| POST | `/api/innings/{id}/retirements/{rid}/return` | Return a retired batter to the crease |
| POST/GET | `/api/series`, `/api/series/{id}` | Create/list series and read its dashboard detail |
| PATCH | `/api/series/{id}` | Edit details/roster and increase or decrease planned length |
| GET | `/api/series/{id}/dashboard` | Explicit dashboard alias with standings, boards, fantasy and awards |
| GET | `/api/auth/session` | Current session, registration availability and auth mode |
| POST | `/api/auth/register` | Bootstrap/login the first account (or register when enabled) |
| POST | `/api/auth/login`, `/api/auth/logout` | Sign in / clear the session |
| PATCH | `/api/auth/password` | Change the signed-in account password |
| GET/PATCH | `/api/users/me` | Signed-in scorer profile (local profile when auth is disabled) |
| GET | `/api/stats/overview` | Totals plus run/wicket/fantasy leaderboards |
| GET | `/api/stats/players` | Full player career statistics |
| GET | `/api/stats/teams` | Team matches, wins, losses, scores and win percentage |

## Frontend CSS

`frontend/css/app.css` is generated by Tailwind and committed so the app needs no
Node runtime. After editing templates or JS class names:

```bash
npm install
npm run build:css      # one-off, minified
npm run watch:css      # during development
```

## Environment variables

Copy `.env.example` to `.env`. The main settings are `DATABASE_URL`,
`GULLY_SECRET_KEY`, `CORS_ORIGINS`, `AUTH_REQUIRED`, `ALLOW_REGISTRATION`,
`SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`, `TRUST_PROXY` and the
`RATE_LIMIT_*` knobs. Production values and the first-account bootstrap flow are
documented in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Testing

```bash
python -m pytest -q
```

The suite uses a throwaway in-memory SQLite database and covers the full T20,
custom and turf workflows plus Phase 5 auth, ownership, CSRF, rate limiting,
pagination, PWA/static assets and security headers. To run the same tests
against PostgreSQL:

```bash
TEST_DATABASE_URL="postgresql+psycopg://gully:gully@localhost:5432/gullyscore_test" python -m pytest
```

Migration drift check and migration smoke test:

```bash
cd backend
flask --app wsgi db check
```

The second revision (`c1543d14e253`) renames `scoring_audit` to `match_events`
while copying every row, and backfills `match_teams`, `match_rules`,
`series_matches` and `matches.owner_id` from existing data. The third revision
(`b7d1e4c9a2f0`) adds retirements, the fantasy ledger, `matches.fantasy_config`
and extended player-stat columns, backfilling `fantasy_config` for existing
matches. The fourth revision (`d2e8a4c7f1b9`) adds the planned series length and
selected team/player snapshots, backfilling the plan from existing matches. The
fifth revision (`f4a9c2d6b8e1`) adds optional authentication fields to users,
series ownership, the `audit_logs` table and composite indexes for paginated
history/detail reads. All upgrade and downgrade paths are implemented.

## Default Custom Turf rules

| Setting | Default |
| --- | --- |
| Overs | 6 |
| Players per team | 5 |
| Balls per over | 6 |
| Wide penalty | 1 |
| Wide counts as legal ball | No |
| No-ball penalty | 1 |
| No-ball counts as legal ball | No |
| Free hit | Enabled |
| Solo batting | Enabled |
| Allowed runs off the bat | 0, 1, 2, 3, 4, 5, 6 |
| Retired player option | Enabled |
| Retirement types | Retired not out, retired out, retired hurt |

Full T20 defaults: 20 overs, 11 a side, 4 overs per bowler, no solo batting.
Custom Match starts T20-shaped with every field editable. All settings are
editable before the match starts; the resolved set is stored on the match and
never rewritten.

## Scoring model in one paragraph

Every ball is a `deliveries` row. The pure scoring engine
(`backend/app/services/scoring_engine.py`) derives runs, extras, legality,
over/ball position, strike rotation, free-hit state and innings completion from
that ball plus an innings snapshot. Recording a delivery locks the innings,
validates against a replay of events, inserts the event, replays aggregates,
rebuilds `player_match_statistics`, rebuilds the itemized `fantasy_points`
ledger and writes a `match_events` row in one transaction. Retirements and
returns are separate innings events anchored to the active-delivery count, so
they replay between the correct balls. Undo marks the last active delivery void
and replays, so totals, strike, free-hit state, scorecards, statistics and
fantasy awards always match the events.

- Wide: `wide_penalty + extra_runs` (e.g. wide + 2 = 3 runs).
- No-ball: `runs_off_bat + no_ball_penalty + extra_runs`.
- Bye / leg bye: `extra_runs`, a legal ball, no penalty.
- Caught/bowled/lbw/stumped cannot carry bat runs; a wide can only produce a
  stumping or running dismissal; a free hit only allows run out, obstruction or
  hitting the ball twice.
- Solo batting means the last batter continues alone, so the innings ends at
  `players_per_team` wickets; otherwise it ends at `players_per_team - 1`.

## Quick API walkthrough

```bash
# 1. Create a Custom Turf match with two 5-player squads
curl -s -X POST http://127.0.0.1:5000/api/matches \
  -H 'Content-Type: application/json' \
  -d '{
    "preset": "custom_turf",
    "team_a": {"name": "Green Caps", "players": ["Arun", "Bilal", "Chetan", "Danish", "Eshan"]},
    "team_b": {"name": "Night Riders", "players": ["Farid", "Gopal", "Harish", "Imran", "Jatin"]},
    "toss": {"winner": "a", "decision": "bat"}
  }'

# 2. Start it (creates both innings)
curl -s -X POST http://127.0.0.1:5000/api/matches/1/start

# 3. Score a ball (bowler_id must belong to the bowling team)
curl -s -X POST http://127.0.0.1:5000/api/innings/1/deliveries \
  -H 'Content-Type: application/json' \
  -d '{"runs_off_bat": 4, "bowler_id": 6}'

# 4. Undo it if needed, then read the scorecard and audit events
curl -s -X POST http://127.0.0.1:5000/api/innings/1/deliveries/undo \
  -H 'Content-Type: application/json' -d '{"reason": "wrong batter"}'
curl -s http://127.0.0.1:5000/api/matches/1/scorecard
curl -s http://127.0.0.1:5000/api/matches/1/events
```

Design decisions: [docs/architecture.md](docs/architecture.md). Deployment and
security: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md),
[docs/SECURITY.md](docs/SECURITY.md). Product and technical specs:
[docs/PRD.md](docs/PRD.md), [docs/TRD.md](docs/TRD.md).

## Data integrity guarantees (Phase 2)

- Deliveries are never deleted; undo voids them with a reason and timestamp.
- `(innings_id, sequence)` and `(innings_id, client_event_id)` are unique. The
  idempotency constraint, not a pre-check, decides duplicates, so a retry or a
  concurrent double submit is recorded exactly once.
- Match creation, every delivery and every undo run in one transaction; a rejected
  command leaves no delivery, aggregate or audit row behind.
- Optional `expected_revision` rejects a stale scorer screen (409).
- Every delivery is validated against the frozen rules: allowed runs, extras,
  dismissal legality per delivery type and free hit, wicket limit, bowler team and
  over quota, striker/non-striker state, and conflicting aliases.
- `legal_balls` is an integer count; illegal deliveries are excluded and overs are
  derived from it without floating point.
- Every delivery, undo, match creation and match start writes a `match_events` row.
- Match rules are frozen at creation; historical rules cannot silently change.
- Innings aggregates, scorecards, results and player statistics are recomputed
  from events, including when a completed chase is reopened by an undo.

## Known limitations (Phase 5)

- Production auth is opt-in and single-scorekeeper oriented; there is no
  password-reset email flow or multi-tenant team management.
- The live pad queues deliveries offline; undo and retirement changes require
  a connection because they need the current server state. Rejected balls are
  kept locally until the scorer discards them and are never retried
  automatically. There is no multi-device realtime sync.
- The fixed-window rate limiter and Flask sessions are process-local. Use one
  Gunicorn worker or add shared storage before scaling out.
- The service worker caches static assets and authenticated GETs for offline
  use; use a dedicated scoring device/profile and clear site data before
  handing the device to someone else.
- Career aggregation groups by player name and team name because squads are
  recreated per match; there is no global player registry yet.
- Fantasy covers batting and bowling (including milestones, maidens, hauls and
  strike-rate/economy bands) but deliberately excludes fielding and captaincy.
- PostgreSQL migrations were generated and applied against SQLite in this
  environment (no PostgreSQL server was available). The schema uses portable
  types and the upgrade/downgrade were exercised on SQLite; run `db upgrade` on a
  PostgreSQL instance before production use. `SELECT … FOR UPDATE` locking is
  PostgreSQL-only and is skipped on SQLite.
