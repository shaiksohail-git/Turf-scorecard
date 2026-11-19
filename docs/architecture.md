# Architecture decisions

## ADR-1: Deliveries are the source of truth (event sourcing)

Each scored ball is one append-only `deliveries` row. Innings totals, strike
positions and scorecards are derived from those rows.

**Why:** corrections, undo and statistics all need a reliable event history.
Storing only running totals makes a wrong ball unrecoverable without guesswork,
and duplicated scoring events become invisible.

**Consequence:** every read path that needs aggregates replays events. At 6–20
overs per innings this is tens to a few hundred rows, so replay is cheap and
always consistent. Cached aggregates on `innings` keep list views fast.

## ADR-2: One engine, frozen rule snapshots

`RuleSet` is a frozen dataclass; presets are values, not code branches in the
scoring path. `matches.rules` stores the resolved snapshot (`rules_version` 1).

**Why:** the brief requires one configurable engine, separate presets, and never
silently changing historical rules. Snapshotting means a later preset change
cannot alter a completed match.

**Consequence:** rule edits only happen before creation; the API never writes
`matches.rules` after insert.

## ADR-3: Pure engine plus deterministic replay

`compute_delivery(rules, snapshot, request)` has no database or Flask imports.
`innings_manager.replay()` rebuilds state from stored events.

**Why:** unit-testable rules, and no divergence between live scoring and
recomputation after a correction.

**Consequence:** replay trusts stored derived values (runs, legality, wicket
type) rather than re-validating old events, so a future validation change cannot
break historical replays.

## ADR-4: Undo is a void, not a delete

`POST /deliveries/undo` marks the last active delivery void with a reason and
replays the innings; the row stays.

**Why:** the brief requires safe undo, audit history, and no silent historical
changes. Deleting rows would also break audit references.

**Consequence:** a voided delivery is excluded from all aggregates but remains
visible with `include_voided=true`. A voided `client_event_id` is not reused
automatically; the scorer records a fresh event.

## ADR-5: Idempotency and optimistic concurrency

- `client_event_id` is optional and unique per innings: a retried submit returns
  the existing delivery with `duplicate: true`.
- `expected_revision` is optional: a mismatch returns 409 `stale_revision`.
- `(innings_id, sequence)` is unique in the database.

**Why:** the brief requires preventing duplicate scoring events; mobile
scorers double-tap and retry.

## ADR-6: Scoring transactions and row locks

Recording a delivery locks the innings row (`SELECT … FOR UPDATE` on
PostgreSQL), validates, inserts, replays aggregates, logs the audit entry and
commits once. Failures roll back.

**Why:** two scorers on the same innings must not interleave writes.

**Consequence:** SQLite (tests) has no row locks; the unique sequence constraint
and tests cover the same invariants.

## ADR-7: Extras encoding

`runs_off_bat` + `extra_type` + `extra_runs`, with penalty from the rules:

- wide: penalty + runs run (e.g. wide + 2 = 3)
- no-ball: bat runs + penalty + additional extras
- bye/leg bye: runs only, legal ball, no penalty

**Why:** one encoding covers every extra without per-rule columns, and totals
are reproducible by replay. Penalty runs exclude strike rotation.

## ADR-8: Solo batting changes how an innings ends

With `solo_batting_enabled`, `max_wickets` equals `players_per_team`: the last
remaining batter continues alone and the innings ends when everyone is out.
Without it, the innings ends at `players_per_team - 1` wickets (last batter not
out).

**Consequence:** a 5-a-side turf innings can end at 5 wickets, and the result
margin uses `max_wickets - wickets`.

## ADR-9: Strike rotation and dismissal placement are simplified

Strike rotates on odd runs physically run, and again at the end of an over. A
dismissed batter is replaced at the end they were standing at after any rotation.
Line decisions like "batters crossed before the catch" are not modelled.

**Why:** it is deterministic, matches how turf scorers record a ball, and covers
all common cases. A full line-decision model is deferred; it can be added as an
optional delivery attribute without changing stored history.

## ADR-10: Static frontend served by Flask

The frontend is plain HTML + compiled Tailwind + ES modules. Flask serves it at
`/` and mounts the API under `/api`, so there is no CORS or build step at runtime.

**Why:** minimal design, fast load, no framework overhead, and a clean separation
of source trees. `frontend/css/app.css` is committed so the app runs without
Node; `npm run build:css` regenerates it.

## ADR-12: Normalized participation tables beside fast lookup columns

`match_teams`, `match_rules` and `series_matches` normalize per-match teams,
the rule snapshot and series membership. `matches.team_a_id`, `team_b_id`,
`rules` and `series_id` stay in place and remain the columns the scoring engine
and list queries read.

**Why:** Phase 1 requires normalized models for match teams, match rules and
series matches, but dropping the existing columns would rewrite the scoring path
and every historical read at once.

**Consequence:** both representations are written in the same transaction, and
the migration backfills the normalized tables from existing matches. The
normalized rows record facts the JSON/columns do not (side, toss winner, bats
first, series position) and are safe to query for reporting. A later revision
can remove the denormalized columns once every read path moves over.

## ADR-13: Player match statistics are a rebuildable projection

`player_match_statistics` is derived, never authoritative. Every innings
recompute (each delivery and each undo) rebuilds the squad's rows from the
scorecard of active deliveries inside the same transaction.

**Why:** the Stats screen needs queryable per-player rows without duplicating
scoring rules in a second place, and undo must never leave stale figures.

**Consequence:** rows for a match are always consistent with its deliveries. A
new match's rows are created on the first scoring action, not on match creation;
the overview totals read innings aggregates so they are correct even before that.

## ADR-14: Shell components and one HTML document per screen

The frontend uses a shared `components/shell.js` (sidebar at `lg`, top bar and
bottom navigation below it, theme toggles) and `components/ui.js` (match cards,
badges, empty/error states). Each screen is its own HTML document with a page
module; there is no client router or framework.

**Why:** the brief asks for HTML/CSS/JS with reusable components and no React or
Node runtime, mobile-first navigation and a dark default theme.

**Consequence:** navigation is a full page load, shared markup is rendered by JS
from one place, and the compiled Tailwind stylesheet is the only build artifact.

## ADR-11: PostgreSQL in production, SQLite for tests

Models use portable types (`JSON`, `Integer`, `String`, `DateTime(timezone=True)`)
so the same schema and code run on both. Alembic owns the schema.

**Why:** tests must not require a database service, while production uses
PostgreSQL as specified.

## ADR-15: Exactly-once scoring through the delivery log

`client_event_id` is an idempotency key generated per ball by the scoring pad.
`deliveries` carries a unique `(innings_id, client_event_id)` constraint and a
unique `(innings_id, sequence)` constraint. The scoring service also takes a row
lock on the innings (`SELECT … FOR UPDATE` on PostgreSQL) before replaying state.

**Why:** a dropped response must be retryable without scoring twice, and two
scorers (or a double tap) must not produce two balls. A pre-check alone is a race;
the database constraint is the authority.

**Consequence:** the loser of an idempotency race rolls back, reloads the stored
delivery and returns it with `duplicate: true`. If two different deliveries race
for the same sequence, the service retries once with a fresh sequence and then
returns `409 delivery_conflict`. The innings row lock serialises concurrent
scorers on PostgreSQL; SQLite (tests, local dev) relies on its write serialisation.

## ADR-16: Two-innings lifecycle and result derivation

Starting a match creates a live first innings and a pending second innings. The
second innings opens automatically when the first completes, with a target of
first-innings runs plus one. Completing the chase derives the result from stored
aggregates: wickets in hand for a successful chase, the run difference when the
defending side wins, or a tie. Undo re-runs the same derivation, so reopening a
finished chase clears `result` and `completed_at` rather than leaving stale data.

**Why:** the result must always match the scorecard, including after a
correction, and the rules for a tie/win are part of scoring rather than UI copy.

**Consequence:** result fields are written only when the second innings
completes, and are cleared when it is reopened. The first innings cannot be
undone once the chase has faced a ball, because that would invalidate the target
the chase is already playing against.

## ADR-17: Retirements are innings events, not deliveries

A retirement is stored in `retirements`, anchored to the number of active
deliveries at the moment it happened (`retired_after_sequence`). Replay applies
retirements and returns between balls. `retired_out` adds a wicket and is final;
`retired_not_out` and `retired_hurt` remove the batter without a wicket and stay
returnable. A non-dismissal retirement of the last batter pauses the innings
instead of ending it.

**Why:** a retirement has no ball, runs or bowler, and forcing it into the
delivery log would corrupt over counts and bowling figures. Anchoring to a
delivery count keeps replay deterministic and lets undo place events correctly.

**Consequence:** scorecards, fall of wickets, partnerships, player statistics
and fantasy awards all read the same retirement rows. Returning a batter fills an
empty crease or queues them for the next vacancy; the card keeps the retirement
history but shows their final innings once they return.

## ADR-19: Series competition views are derived, never stored beside matches

A series stores only planning metadata: its name, default format/preset,
planned length and optional selected team/player snapshots. Standings, batting
and bowling boards, fantasy splits and awards are rebuilt on read from completed
matches, active deliveries, retirements and each match's fantasy ledger.

**Why:** the brief requires corrections to recalculate series leaderboards,
exactly-once counting and separation from individual match statistics. A second
set of stored series totals would be a projection with no transactional link to
the scoring path and could drift after undo.

**Consequence:** a match is included exactly once by `series.matches` and only
while its status is `completed`; reopening a chase immediately removes it from
the dashboard. Editing the planned length or roster never touches a match, its
frozen rules or its result. Awards are derived deterministically with unique
`award_key` values and winner arrays that preserve ties. Rate boards apply fixed
qualification thresholds and return only qualified players.

## ADR-18: Fantasy points are a rebuildable ledger

`fantasy_points` is a projection with an itemized row per award and a unique
`(match_id, source_key)` constraint. Every scoring or retirement transaction
deletes the match's ledger and rebuilds it from the active events. The match
pins a `fantasy_config` (`t20` or `short`) so later config changes cannot alter
historical points.

**Why:** milestones, maidens and hauls must not be awarded twice, and undo must
remove awards for voided balls. A ledger also makes the calculation auditable
instead of exposing only a total.

**Consequence:** the ledger is never authoritative on its own; it is always
reproducible from deliveries and retirements. Fielding and captaincy points are
deliberately absent, and the two format configurations have independent
strike-rate and economy bands.
