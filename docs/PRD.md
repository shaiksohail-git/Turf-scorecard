# GullyScore — Product Requirements (Phase 1)

## 1. Problem

Turf and gully cricket groups score matches in chat threads or on paper. Scores
drift, extras rules differ between groups, corrections lose history, and there is
no reliable record for stats or fantasy points. Existing apps assume full 11-a-side
T20 or force fixed rules.

## 2. Product goal

A fast, phone-first scorer that keeps one configurable rule engine for every
format, stores every delivery as an auditable event, and makes corrections safe.
Scorekeeping must be possible with one thumb while standing at the ground.

## 3. Users

| Persona | Need |
| --- | --- |
| Scorer | Record deliveries in seconds, undo mistakes, never double-count a ball |
| Team captain | Configure rules before the toss, see a correct scorecard |
| Group organiser | Run a series of matches without losing completed results |
| Viewer | Read a clear scorecard and rule summary |

## 4. Functional requirements

### Rules
- FR-1: Three presets — Full T20, Custom Match, Custom Turf — resolved by one engine.
- FR-2: Custom Turf defaults: 6 overs, 5 players, 6 balls/over, wide penalty 1,
  wide not a legal ball, no-ball penalty 1, no-ball not a legal ball, free hit on,
  solo batting on, allowed runs 0–6, retired player option on.
- FR-3: Retirement types: retired not out, retired out, retired hurt.
- FR-4: Every rule is editable before the match starts; edits are validated with
  precise field-level errors.
- FR-5: A match stores an immutable snapshot of its resolved rules.

### Scoring
- FR-6: Record runs, wide, no-ball, bye, leg bye, wicket and free hit per delivery.
- FR-7: Derive over/ball position, legality, extras, strike rotation, free hit
  carry-over and innings completion deterministically.
- FR-8: Reject invalid deliveries with a stable error code (e.g. caught off a wide).
- FR-9: Prevent duplicate deliveries through a client event id and a stale-revision guard.
- FR-10: Undo the last delivery without deleting it; keep an audit entry.
- FR-11: Recompute innings aggregates and the scorecard from events after every change.
- FR-12: Second innings starts with a target of first-innings runs + 1; the match
  finishes with a runs/wickets/tie result.

### Data
- FR-13: Store teams, players, series, matches, innings, deliveries and audit entries.
- FR-14: Never delete completed match records when a series changes.
- FR-15: Keep scoring mutations transactional and serialisable per innings.

### Interface
- FR-16: Minimal, mobile-first layout; dark by default with a light toggle; green accent.
- FR-17: Large touch targets and accessible focus/label/status handling.
- FR-18: Clear loading, success and error states.

## 5. Out of scope for Phase 1

- Interactive scoring pad (Phase 2), retirement and solo-batting UI flows (Phase 2).
- Series editing and match rescheduling (Phase 3).
- Fantasy points and full tournament statistics (Phase 4).
- User accounts and multi-device live sync.

## 6. Phase plan

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Foundation: schema, migrations, rules engine, scoring engine, innings lifecycle, undo/audit, read APIs, static frontend shell | Complete |
| 2 | Scoring pad UI, wickets and retirement flows, solo batting behaviour in the UI | Planned |
| 3 | Series management, corrections beyond undo, richer match lifecycle | Planned |
| 4 | Statistics, fantasy points (itemised), leaderboards | Planned |
| 5 | Performance and accessibility hardening, deployment polish | Planned |

## 7. Success criteria for Phase 1

- Rule defaults match the specification exactly and are covered by tests.
- An all-dot one-over innings ends the innings; the chase reaches a stored result.
- Undo restores totals, strike and free-hit state from events.
- Duplicate submissions never create two deliveries.
- The API and migrations run against the documented database configuration.
