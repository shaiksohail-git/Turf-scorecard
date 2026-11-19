# GullyScore API (Phase 5)

Base path: `/api`. All responses are JSON.

- Success: `{"data": ...}`; list endpoints may add `"meta"`.
- Failure: `{"error": {"code": "...", "message": "...", "details": {...}}}`
- Mutating endpoints accept an optional `X-Actor` header (default `scorer`) that
  is stored in the audit trail.

## Authentication and authorization

Authentication is optional locally (`AUTH_REQUIRED=false`) and recommended in
production. When enabled, protected `/api/*` requests require the signed session
cookie and every `POST`/`PUT`/`PATCH`/`DELETE` request must send
`X-CSRF-Token` matching the session token.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/auth/session` | Session state, auth mode and whether registration is open |
| POST | `/api/auth/register` | First account (always allowed) or a new account when registration is open |
| POST | `/api/auth/login` | Email/password sign-in; returns the CSRF token |
| POST | `/api/auth/logout` | Clear the session (CSRF required) |
| PATCH | `/api/auth/password` | Change the current password |

Passwords use salted Werkzeug hashes and must be 10–256 characters. Match and
series detail/list endpoints are owner-scoped when auth is enabled; cross-owner
access returns `403 forbidden`. Unauthenticated protected API calls return
`401 authentication_required`; missing/invalid CSRF returns `403 csrf_failed`.

## Request limits

`MAX_CONTENT_LENGTH` is 1 MiB. Rate limits are fixed windows per process and
return `429 rate_limited` with `Retry-After`. Authentication endpoints default
to 10 requests/minute and scoring endpoints to 300/minute; general API calls
use 1000/minute. Override them with the `RATE_LIMIT_*` environment variables.

## Transaction and concurrency guarantees

Every scoring command is one database transaction:

- `POST /api/matches` writes teams, players, the match, normalized rules/team
  rows, any series link and the audit row together. A validation failure leaves
  no partial rows.
- `POST /api/innings/{id}/deliveries` locks the innings row (PostgreSQL), replays
  the active deliveries, validates the command, inserts exactly one delivery,
  recomputes innings aggregates and player statistics, writes the audit row and
  then commits. Any rule violation or conflict rolls the whole command back.
- `POST /api/innings/{id}/deliveries/undo` voids the last delivery, replays and
  commits in the same transaction. Deliveries are never deleted.

Every delivery is validated by the pure scoring engine: run values against
`allowed_runs`, extra type and penalties, wicket type per delivery type and free
hit, dismissed batter role, wicket limit, bowler ownership, bowler over quota,
striker/non-striker agreement and `expected_revision`. Two aliases supplied with
different values (`runs` vs `runs_off_bat`, `extra` vs `extra_type`) are rejected.

### Exactly once

`client_event_id` is an idempotency key. The unique
`(innings_id, client_event_id)` constraint is authoritative, not the pre-check,
so two concurrent submits of the same event cannot both score. The loser of the
race returns the stored delivery with `duplicate: true` and `200`, which also
makes a lost response safe to retry. `(innings_id, sequence)` is unique as well.

### Legal balls

`legal_balls` is an integer count of legal deliveries. Wides and no-balls are
excluded unless the rules make them legal; byes and leg-byes are included. Overs
are rendered from that integer as `overs.balls` (`7` → `1.1`), with no floating
point used for ball counts.

## Health

### `GET /api/health`
`200` with app name/version, database status and server time. `503` if the
database cannot be reached.

## Rules

### `GET /api/rules/presets`
Returns the three presets, their resolved rules, derived values (`total_balls`,
`max_wickets`) and the accepted extra/wicket/retirement type lists.

### `POST /api/rules/validate`
```json
{ "preset": "custom_turf", "rules": { "overs": 4, "wide_penalty": 2 } }
```
`200` with the resolved rules, or `422` with a field-level error. Unknown
Override keys are rejected.

## Matches

### `POST /api/matches`
```json
{
  "preset": "custom_turf",
  "rules": { "overs": 6 },
  "series_id": null,
  "venue": "Local turf",
  "team_a": { "name": "Green Caps", "players": ["Arun", "Bilal", "Chetan", "Danish", "Eshan"] },
  "team_b": { "name": "Night Riders", "players": ["Farid", "Gopal", "Harish", "Imran", "Jatin"] },
  "toss": { "winner": "a", "decision": "bat" }
}
```
Creates teams, players and a draft match with a frozen rules snapshot. Each
squad must contain exactly `players_per_team` players; the submitted order is the
batting order. An optional `fantasy_config` of `t20` or `short` pins the fantasy
engine; otherwise it is derived from the preset and innings length. `201`.

### `GET /api/matches?page=1&per_page=20&status=live&series_id=1`
List match summaries, newest first, with pagination metadata:
```json
{
  "data": [ ... ],
  "meta": { "page": 1, "per_page": 20, "total": 42, "has_more": true }
}
```
`page` starts at 1; `per_page` is 1–100. The legacy `limit` parameter is still
accepted when `per_page` is absent. When auth is enabled the list only returns
the signed-in owner's matches (plus legacy unowned rows).

### `GET /api/matches/{id}`
Full match detail: rules snapshot, teams with players, innings summaries, toss and result.

### `POST /api/matches/{id}/start`
Creates innings 1 (live) and innings 2 (pending) from the toss, then puts the
match live. `409` if the match is not a draft.

### `GET /api/matches/{id}/scorecard`
Returns `match`, `rules`, and one card per innings with totals, extras,
batting and bowling lines, `fall_of_wickets`, `partnerships`, `retirements`,
ball-by-ball `commentary` and live `state`.

### `GET /api/matches/{id}/events?limit=50`
Audit timeline, newest first: `match.created`, `match.started`,
`delivery.recorded` and `delivery.voided`, each with `actor`, `payload` and
`created_at`. Rows come from `match_events`.

## Scoring

### `GET /api/innings/{id}`
Live state: runs, wickets, overs, striker/non-striker, pending free hit, target,
runs needed, balls remaining, revision, `solo_mode`, `can_score`,
`retired_active_ids`, `retired_out_ids` and `available_player_ids`.

### `POST /api/innings/{id}/deliveries`
```json
{
  "runs_off_bat": 4,
  "bowler_id": 12,
  "striker_id": 3,
  "non_striker_id": 4,
  "client_event_id": "device-1-0007",
  "expected_revision": 6
}
```
`runs` is accepted as an alias for `runs_off_bat`. `bowler_id` is required and
must belong to the bowling team. `striker_id` / `non_striker_id` are optional
but must match the current replay state if supplied.

Wicket example:
```json
{ "runs_off_bat": 0, "bowler_id": 12, "is_wicket": true, "wicket_type": "bowled" }
```

`201` with `{delivery, state, duplicate: false}`. A repeated `client_event_id`
returns `200` with `duplicate: true` and the original delivery; it is not scored
again, even if the innings has completed since. Concurrent duplicates are
resolved by the database constraint and follow the same path.

Extras:
| Type | Runs counted |
| --- | --- |
| `wide` | `wide_penalty + extra_runs` |
| `no_ball` | `runs_off_bat + no_ball_penalty + extra_runs` |
| `bye` / `leg_bye` | `extra_runs` (legal ball) |

`dismissed_player` is `striker` (default) or `non_striker`; the non-striker can
only be run out. Wicket types: `bowled`, `caught`, `lbw`, `stumped`, `run_out`,
`hit_wicket`, `obstructing_the_field`, `hit_the_ball_twice`, `timed_out`.

### `GET /api/innings/{id}/deliveries?include_voided=true`
Delivery events in scoring order.

### `POST /api/innings/{id}/deliveries/undo`
```json
{ "reason": "wrong batter" }
```
Marks the last active delivery void, replays the innings and writes an audit
entry. `409` (`nothing_to_undo`, `later_innings_started`). Undoing the last ball
of a completed chase reopens the match (`result` cleared) so it can be corrected
and re-scored.

## Retirements

Retirements are innings events, not deliveries. They are anchored to the number
of active deliveries at the time and replay between balls. `retired_out` adds a
wicket and cannot return; `retired_not_out` and `retired_hurt` add no wicket and
remain returnable. Retiring the last batter without a dismissal pauses the
innings; it does not end it.

### `GET /api/innings/{id}/retirements`
Returns the innings retirement history with player, type, reason, replacement,
`retired_at`, `returned_at` and `can_return`.

### `POST /api/innings/{id}/retirements`
Body: `player_id` (must be at the crease), `retirement_type` (one of the rules
values), optional `reason` (max 200 characters) and optional
`replacement_player_id`. Without a replacement the next eligible batter comes in;
if none exists the innings waits. `201` with the retirement and new `state`.
Validation errors return `422`; disabled retirements return `409
retirements_disabled`.

### `POST /api/innings/{id}/retirements/{retirement_id}/return`
Marks the batter returnable and puts them back at an empty crease, or queues them
for the next vacancy. `409 retired_out_cannot_return`, `already_returned`,
`batter_out` or `innings_not_live` when the command is not allowed.

## Fantasy points

### `GET /api/matches/{id}/fantasy?player_id=12`
Returns the pinned `config` (`t20` or `short`), per-player `totals`, and the
itemized `ledger`. Every ledger row has a `category`, `points`, `detail` and
unique `source_key`. The ledger is rebuilt from active deliveries and retirements
after every scoring action and undo, so a voided ball cannot leave an award
behind. Fielding and captaincy points are not modelled.

The default scoring is: run +1, four +4, six +6, 25 runs +4, 50 +8, 100 +16,
eligible duck -2, wicket +25, bowled/LBW +8, maiden +12, 3-wicket haul +4,
4-wicket haul +8 and 5-wicket haul +16. Strike-rate and economy bands are
configured separately for T20 and short-format matches.

## Two innings and results

Starting a match creates innings 1 (`live`) and innings 2 (`pending`). When
innings 1 completes (scheduled balls, all out, or a target), innings 2 becomes
`live` with `target = first innings runs + 1`; its state exposes `runs_needed`
and `balls_remaining`.

When innings 2 completes, the match moves to `completed` and `result` is set:

| Situation | `outcome` | `margin` | `winner_team_id` |
| --- | --- | --- | --- |
| Chase reaches the target | `wickets` | wickets in hand | chasing team |
| Chase is all out or out of balls behind | `runs` | run difference | defending team |
| Scores level | `tie` | `0` | `null` |

`result.summary` is the display string, for example `"Bravo won by 1 wicket(s)"`
or `"Match tied"`. The scorecard endpoint returns both innings with full batting,
bowling and extras figures computed from the active deliveries.

## Series

### `POST /api/series`
```json
{
  "name": "Sunday Turf Cup",
  "preset": "custom_turf",
  "format": "custom_turf",
  "planned_matches": 6,
  "team_a": { "name": "Green Caps", "players": ["Arun", "Bilal"] },
  "team_b": { "name": "Night Riders", "players": ["Farid", "Gopal"] },
  "start_date": "2026-11-08",
  "end_date": "2026-11-30",
  "notes": "Home and away"
}
```
Creates a series and returns its dashboard detail. `preset` must be one of the
three rules presets when supplied. Both teams are optional, but if a roster is
selected both team names are required, players must be unique non-empty names,
and the two team names must differ. `planned_matches` is `0`–`1000`.

### `GET /api/series?limit=20`
List series summaries, newest first. Each summary includes `planned_matches`,
`team_a`, `team_b`, `match_count`, `matches_played` and `matches_remaining`.

### `GET /api/series/{id}` and `GET /api/series/{id}/dashboard`
Return series metadata, linked `matches`, and the derived dashboard:

- `standings`: team, played, wins, losses, ties, points, win percentage/rank.
- `mvp_leaderboard` / `fantasy_leaderboard`: total and split fantasy points.
- `match_fantasy`: per-match player totals with batting and bowling splits.
- `batting_leaderboards`: `runs`, `highest_score`, `average`, `strike_rate`,
  `fours`, `sixes`, `fifties` and `centuries`.
- `bowling_leaderboards`: `wickets`, `economy`, `best_figures`, `average`,
  `strike_rate`, `maidens` and `dot_balls`.
- `recent_results`: the five newest completed matches.
- `awards`: `player_of_match` (one entry per completed match), `best_batter`,
  `best_bowler` and `player_of_series`. Winner arrays support ties and have
  stable, unique `award_key` values.
- `qualification`: the thresholds used by rate-based boards.

Only `completed` matches contribute to standings, boards, fantasy and awards.
Every read rebuilds the figures from active deliveries, retirements and the
fantasy ledger, so corrections and undos are reflected immediately and a match
is counted exactly once. Rate boards hide unqualified players: batting average
needs 2 innings and a dismissal, batting strike rate 30 balls, bowling economy
12 legal balls, and bowling average/strike rate 2 wickets.

Player of the Series is the highest cumulative fantasy total across completed
series matches; batting/bowling splits exclude fielding and captaincy. Tied
winners are all returned, ordered deterministically by the relevant cricket
figures and then player/team name.

### `PATCH /api/series/{id}`
Partial edit of `name`, `preset`, `format`, `planned_matches`, `start_date`,
`end_date`, `notes`, `team_a` and `team_b`. The planned length may decrease but
may never be lower than the number of completed linked matches (`422` with
`details.minimum`). Editing never deletes a match or rewrites a match's rules
snapshot, result or statistics.

A match created with `series_id` also writes a `series_matches` row with its
position inside the series. `end_date` before `start_date` is rejected.

## Users

With auth disabled, a single local user (`Local Scorer`) is created on first use,
owns every new match and backs the Settings profile. With auth enabled, the
signed-in user backs the profile and owns newly created matches and series.

### `GET /api/users/me`
`{ id, display_name, email, is_active, created_at }`.

### `PATCH /api/users/me`
```json
{ "display_name": "Ayesha", "email": "ayesha@example.com" }
```
`display_name` must be 2–60 characters. `email` may be `null` to clear it.
`422` on invalid input.

## Statistics

### `GET /api/stats/overview?limit=5`
```json
{
  "totals": { "matches": 3, "matches_live": 1, "matches_completed": 2,
              "teams": 6, "players": 30, "runs": 412, "wickets": 24, "legal_balls": 288 },
  "top_run_scorers": [ { "player_id": 4, "player_name": "Arun", "team_name": "Green Caps",
                         "runs": 96, "wickets": 0, "matches": 3, "label": "runs" } ],
  "top_wicket_takers": []
}
```
Totals come from stored innings aggregates; leaderboards aggregate
`player_match_statistics`, which is rebuilt from deliveries and retirements after
every ball and undo, so the numbers always match the scorecards. The response
also includes `top_fantasy_scorers` and `teams`.

### `GET /api/stats/players?limit=50`
Career rows grouped by player and team name: matches, innings, runs, highest
score, batting average, strike rate, fours, sixes, not-outs, wickets, bowling
average, economy, best bowling and fantasy points.

### `GET /api/stats/teams`
Matches, completed matches, wins, losses, ties, highest and lowest score, and win
percentage (wins divided by completed matches).

## Common error codes

| Code | Meaning |
| --- | --- |
| `validation_error` | Malformed or invalid payload |
| `not_found` | Unknown match/innings/series |
| `conflict` | State conflict (match not live, nothing to undo) |
| `runs_not_allowed` | Bat runs outside the preset's allowed set |
| `invalid_extra_type` | Unknown extra |
| `wicket_not_allowed_off_wide` / `_off_no_ball` / `_on_free_hit` | Illegal dismissal combination |
| `wicket_runs_conflict` | Caught/bowled/lbw/stumped with bat runs |
| `no_non_striker` | Non-striker dismissal with no non-striker |
| `innings_complete` | Scoring after the innings ended |
| `match_not_live` / `innings_not_live` | Scoring before start or after completion |
| `stale_revision` | `expected_revision` no longer matches |
| `bowler_over_limit` | Bowler exceeded `max_overs_per_bowler` |
| `conflicting_fields` | `runs`/`runs_off_bat` or `extra`/`extra_type` disagree |
| `invalid_client_event_id` | Idempotency key is empty or longer than 64 characters |
| `delivery_conflict` | Two different deliveries raced for the same sequence; reload and retry |
| `no_striker` | No batter is at the crease; a retired batter may need to return |
| `solo_batting_disabled` | One batter remains but solo batting is off for this match |
| `retirements_disabled` | The match rules do not allow retirements |
| `retired_out_cannot_return` | A retired out batter is permanently out |
| `already_retired` / `already_returned` / `batter_out` | Invalid retirement or return transition |
| `player.retired` / `player.returned` | Audit event types written for retirement history |
| `authentication_required` | The API requires a signed-in session |
| `invalid_credentials` | Sign-in failed |
| `csrf_failed` | Missing or invalid `X-CSRF-Token` |
| `registration_disabled` | Registration is closed after bootstrapping |
| `forbidden` | Authenticated user does not own the match/series |
| `rate_limited` | Too many requests in the current window |

Security events are stored in `audit_logs`; match actions remain in the
append-only `match_events` timeline.
