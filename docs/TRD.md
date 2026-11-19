# GullyScore — Technical Requirements (Phase 1)

## 1. Stack

| Layer | Choice |
| --- | --- |
| Frontend | Static HTML, Tailwind CSS (compiled), ES modules — no framework |
| API | Python 3.13, Flask 3, blueprints under `/api` |
| ORM / migrations | SQLAlchemy 2, Flask-SQLAlchemy, Alembic via Flask-Migrate |
| Database | PostgreSQL (production), SQLite (automated tests only) |
| Tests | pytest with an isolated in-memory SQLite database |

The frontend and backend are separate source trees. Flask serves the static
frontend for same-origin convenience and exposes the JSON API; `API_BASE` in
`frontend/js/api.js` can point the same files at a separately hosted API.

## 2. Module map

```
backend/app/
  errors.py            ApiError / ValidationError / DeliveryValidationError
  models/              Team, Player, Series, Match, Innings, Delivery, ScoringAudit
  services/
    rules_engine.py    RuleSet dataclass, presets, override validation
    scoring_engine.py  Pure per-delivery computation, no database access
    innings_manager.py Replay, transactional delivery recording, undo, lifecycle
    match_manager.py   Match creation (rules snapshot) and start
    statistics.py      Scorecard and aggregate derivation from events
    scorecard.py       Read-only match scorecard composition
    series_manager.py  Series create/read
  routes/              health, rules, matches, scoring, series
  utils/               serialisers and request helpers
```

## 3. Data model

| Table | Purpose | Key constraints |
| --- | --- | --- |
| `teams` | Team identity and batting squad | name indexed |
| `players` | Squad members with role and batting order | role in enum check |
| `series` | Groups matches; never owns match deletion | optional preset |
| `matches` | Match, teams, toss, immutable `rules` JSON snapshot | distinct teams, status check, `rules_version >= 1` |
| `innings` | Per-innings aggregates, batting order, target | unique `(match_id, number)`, non-negative totals |
| `deliveries` | Append-only delivery events | unique `(innings_id, sequence)`, unique `(innings_id, client_event_id)`, non-negative runs |
| `scoring_audit` | Who did what, when, with payload | indexed by match and action |

Aggregates (`innings.total_runs`, `wickets`, `legal_balls`) are caches derived
only from active deliveries. They are rewritten by replay, never incremented
independently.

## 4. Scoring algorithm

For each delivery the engine receives the frozen `RuleSet`, an
`InningsSnapshot` (legal balls, wickets, runs, pending free hit, striker,
non-striker, target, completion flag) and a `DeliveryRequest`.

1. Reject if the innings is complete.
2. Validate the extra type, run values against `allowed_runs`, and the
   extra/run combination (no bat runs off a wide or bye, byes need a run).
3. Validate the wicket: known type, legal for the delivery type, legal on a
   free hit, zero bat runs where required, valid dismissal role, wickets left.
4. Penalty and extras:
   - wide: `wide_penalty + extra_runs`
   - no-ball: `runs_off_bat + no_ball_penalty + extra_runs`
   - bye/leg bye: `extra_runs` (legal ball, no penalty)
5. Legality: wide/no-ball follow the rule flags; everything else is legal.
6. Position: `over = legal_balls // balls_per_over + 1`,
   `ball = legal_balls % balls_per_over + 1`.
7. Strike rotation uses runs physically run (`runs_off_bat + extra_runs`), so
   penalty runs never rotate the strike.
8. Free hit next is true after a no-ball, and persists if a free-hit delivery
   is itself illegal.
9. Completion when legal balls reach the innings length, wickets reach the
   limit, or the target is reached.

The engine is pure: no database, no Flask. Recording and replay both use it.

## 5. Transactions, idempotency and concurrency

- Each scoring mutation runs in one transaction: optional `SELECT … FOR UPDATE`
  on the innings row (PostgreSQL; skipped on SQLite), delivery insert, aggregate
  replay, audit insert, commit. Any exception rolls back.
- `client_event_id` is unique per innings; repeating it returns the existing
  delivery with `duplicate: true` and HTTP 200 instead of scoring twice.
- `expected_revision` optionally guards against stale scorer screens (HTTP 409
  `stale_revision`).
- `(innings_id, sequence)` is unique as a database backstop.

## 6. Undo and corrections

Undo marks the last active delivery `is_voided`, stores a reason and timestamp,
replays the innings, and writes an audit entry. The delivery row remains, so the
original event and its void reason are both auditable. Reopening a completed
first innings parks the second innings again if the chase had not started;
undoing while the chase has begun is rejected.

## 7. Validation and errors

Every error uses `{"error": {"code", "message", "details"}}`.
`DeliveryValidationError` codes include `runs_not_allowed`, `invalid_extra_type`,
`wicket_not_allowed_off_wide`, `wicket_not_allowed_on_free_hit`,
`wicket_runs_conflict`, `no_non_striker`, `innings_complete`. Lifecycle errors
use `match_not_live`, `innings_not_live`, `stale_revision`, `nothing_to_undo`,
`bowler_over_limit`.

## 8. Testing strategy

- Unit tests for rules presets, overrides, snapshot round-trips.
- Engine tests for runs, extras, wickets, free hits, completion.
- API tests for match creation, start, scoring, idempotency, undo, scorecard,
  lifecycle result and series.
- Tests run on SQLite with portable column types; the schema is PostgreSQL
  compatible and Alembic migrations are the source of truth.

## 9. Deployment notes

- `flask --app wsgi db upgrade` applies migrations.
- `python wsgi.py` runs the development server; `waitress-serve --call` is
  suitable for Windows production serving (see README).
- Secrets come from environment variables; `.env` is ignored by git.
