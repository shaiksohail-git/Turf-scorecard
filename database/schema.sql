-- GullyScore reference schema for PostgreSQL.
--
-- The Alembic migrations in backend/migrations are the source of truth; this
-- file mirrors revision f4a9c2d6b8e1 for review and read-only tooling.
--
-- Design notes:
--   * deliveries is append-only; a correction marks a row void instead of
--     deleting it.
--   * matches.rules holds the immutable, resolved rule snapshot for that match.
--   * matches.team_a_id / team_b_id / series_id remain fast lookup columns while
--     match_teams and series_matches hold the normalized participation rows.
--   * player_match_statistics is a projection rebuilt from delivery events.
--   * innings totals are caches derived from deliveries and rewritten on replay.

CREATE TABLE users (
    id           SERIAL PRIMARY KEY,
    display_name VARCHAR(60) NOT NULL,
    email        VARCHAR(160) UNIQUE,
    password_hash VARCHAR(255),
    last_login_at TIMESTAMPTZ,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL
);

CREATE TABLE audit_logs (
    id          SERIAL PRIMARY KEY,
    action      VARCHAR(64) NOT NULL,
    actor       VARCHAR(64) NOT NULL DEFAULT 'anonymous',
    user_id     INTEGER REFERENCES users (id) ON DELETE SET NULL,
    ip_address  VARCHAR(64),
    user_agent  VARCHAR(255),
    details     JSON,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_audit_logs_action ON audit_logs (action);
CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);
CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE TABLE series (
    id               SERIAL PRIMARY KEY,
    owner_id         INTEGER REFERENCES users (id) ON DELETE SET NULL,
    name             VARCHAR(120) NOT NULL,
    format           VARCHAR(24) NOT NULL DEFAULT 'custom',
    preset           VARCHAR(32),
    planned_matches  INTEGER NOT NULL DEFAULT 0,
    team_a_name      VARCHAR(80),
    team_b_name      VARCHAR(80),
    team_a_players   JSON,
    team_b_players   JSON,
    start_date       DATE,
    end_date         DATE,
    notes            TEXT,
    created_at       TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL
);

CREATE TABLE teams (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(80) NOT NULL,
    short_name  VARCHAR(16),
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_teams_name ON teams (name);

CREATE TABLE players (
    id            SERIAL PRIMARY KEY,
    team_id       INTEGER NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
    name          VARCHAR(80) NOT NULL,
    role          VARCHAR(24) NOT NULL DEFAULT 'batter',
    batting_order INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_players_role CHECK (role IN ('batter', 'bowler', 'all_rounder', 'wicketkeeper'))
);
CREATE INDEX ix_players_team_id ON players (team_id);

CREATE TABLE matches (
    id                     SERIAL PRIMARY KEY,
    series_id              INTEGER REFERENCES series (id) ON DELETE SET NULL,
    team_a_id              INTEGER NOT NULL REFERENCES teams (id),
    team_b_id              INTEGER NOT NULL REFERENCES teams (id),
    owner_id               INTEGER REFERENCES users (id) ON DELETE SET NULL,
    venue                  VARCHAR(120),
    preset                 VARCHAR(32) NOT NULL,
    rules                  JSON NOT NULL,
    rules_version          INTEGER NOT NULL DEFAULT 1,
    fantasy_config         VARCHAR(16) NOT NULL DEFAULT 'short',
    status                 VARCHAR(16) NOT NULL DEFAULT 'draft',
    toss_winner_id         INTEGER REFERENCES teams (id),
    toss_decision          VARCHAR(8),
    batting_first_team_id  INTEGER REFERENCES teams (id),
    result                 JSON,
    started_at             TIMESTAMPTZ,
    completed_at           TIMESTAMPTZ,
    revision               INTEGER NOT NULL DEFAULT 0,
    created_at             TIMESTAMPTZ NOT NULL,
    updated_at             TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_matches_distinct_teams CHECK (team_a_id <> team_b_id),
    CONSTRAINT ck_matches_status CHECK (status IN ('draft', 'live', 'completed', 'abandoned')),
    CONSTRAINT ck_matches_toss_decision CHECK (toss_decision IS NULL OR toss_decision IN ('bat', 'bowl')),
    CONSTRAINT ck_matches_rules_version CHECK (rules_version >= 1)
);
CREATE INDEX ix_matches_series_id ON matches (series_id);
CREATE INDEX ix_matches_status ON matches (status);
CREATE INDEX ix_matches_team_a_id ON matches (team_a_id);
CREATE INDEX ix_matches_team_b_id ON matches (team_b_id);
CREATE INDEX ix_matches_owner_id ON matches (owner_id);
CREATE INDEX ix_matches_status_id ON matches (status, id);
CREATE INDEX ix_matches_series_id_id ON matches (series_id, id);
CREATE INDEX ix_matches_owner_id_id ON matches (owner_id, id);
CREATE INDEX ix_series_owner_id ON series (owner_id);
CREATE INDEX ix_series_owner_id_id ON series (owner_id, id);

CREATE TABLE match_teams (
    id             SERIAL PRIMARY KEY,
    match_id       INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
    team_id        INTEGER NOT NULL REFERENCES teams (id),
    side           VARCHAR(1) NOT NULL,
    is_toss_winner BOOLEAN NOT NULL DEFAULT FALSE,
    bats_first     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_match_teams_match_side UNIQUE (match_id, side),
    CONSTRAINT uq_match_teams_match_team UNIQUE (match_id, team_id),
    CONSTRAINT ck_match_teams_side CHECK (side IN ('a', 'b'))
);
CREATE INDEX ix_match_teams_match_id ON match_teams (match_id);
CREATE INDEX ix_match_teams_team_id ON match_teams (team_id);

CREATE TABLE match_rules (
    id                         SERIAL PRIMARY KEY,
    match_id                   INTEGER NOT NULL UNIQUE REFERENCES matches (id) ON DELETE CASCADE,
    preset                     VARCHAR(32) NOT NULL,
    version                    INTEGER NOT NULL DEFAULT 1,
    overs                      INTEGER NOT NULL,
    balls_per_over             INTEGER NOT NULL,
    players_per_team           INTEGER NOT NULL,
    wide_penalty               INTEGER NOT NULL,
    wide_counts_as_legal_ball  BOOLEAN NOT NULL DEFAULT FALSE,
    no_ball_penalty            INTEGER NOT NULL,
    no_ball_counts_as_legal_ball BOOLEAN NOT NULL DEFAULT FALSE,
    free_hit_enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    solo_batting_enabled       BOOLEAN NOT NULL DEFAULT FALSE,
    allowed_runs               JSON NOT NULL,
    retired_player_option      BOOLEAN NOT NULL DEFAULT TRUE,
    retirement_types           JSON NOT NULL,
    max_overs_per_bowler       INTEGER,
    created_at                 TIMESTAMPTZ NOT NULL,
    updated_at                 TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_match_rules_overs CHECK (overs >= 1 AND balls_per_over >= 1),
    CONSTRAINT ck_match_rules_players CHECK (players_per_team >= 2 AND players_per_team <= 11),
    CONSTRAINT ck_match_rules_version CHECK (version >= 1)
);
CREATE INDEX ix_match_rules_match_id ON match_rules (match_id);

CREATE TABLE series_matches (
    id         SERIAL PRIMARY KEY,
    series_id  INTEGER NOT NULL REFERENCES series (id) ON DELETE CASCADE,
    match_id   INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_series_matches_pair UNIQUE (series_id, match_id)
);
CREATE INDEX ix_series_matches_series_id ON series_matches (series_id);
CREATE INDEX ix_series_matches_match_id ON series_matches (match_id);

CREATE TABLE innings (
    id                SERIAL PRIMARY KEY,
    match_id          INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
    number            INTEGER NOT NULL,
    batting_team_id   INTEGER NOT NULL REFERENCES teams (id),
    bowling_team_id   INTEGER NOT NULL REFERENCES teams (id),
    status            VARCHAR(16) NOT NULL DEFAULT 'pending',
    batting_order     JSON NOT NULL,
    total_runs        INTEGER NOT NULL DEFAULT 0,
    wickets           INTEGER NOT NULL DEFAULT 0,
    legal_balls       INTEGER NOT NULL DEFAULT 0,
    target            INTEGER,
    revision          INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_innings_match_number UNIQUE (match_id, number),
    CONSTRAINT ck_innings_status CHECK (status IN ('pending', 'live', 'completed')),
    CONSTRAINT ck_innings_number CHECK (number >= 1),
    CONSTRAINT ck_innings_totals CHECK (total_runs >= 0 AND wickets >= 0 AND legal_balls >= 0)
);
CREATE INDEX ix_innings_match_id ON innings (match_id);

CREATE TABLE deliveries (
    id                   SERIAL PRIMARY KEY,
    innings_id           INTEGER NOT NULL REFERENCES innings (id) ON DELETE CASCADE,
    sequence             INTEGER NOT NULL,
    client_event_id      VARCHAR(64),
    over_number          INTEGER NOT NULL,
    ball_in_over         INTEGER NOT NULL,
    striker_id           INTEGER NOT NULL REFERENCES players (id),
    non_striker_id       INTEGER REFERENCES players (id),
    bowler_id            INTEGER NOT NULL REFERENCES players (id),
    runs_off_bat         INTEGER NOT NULL DEFAULT 0,
    extra_type           VARCHAR(16),
    extra_runs           INTEGER NOT NULL DEFAULT 0,
    penalty_runs         INTEGER NOT NULL DEFAULT 0,
    total_runs           INTEGER NOT NULL DEFAULT 0,
    is_legal_ball        BOOLEAN NOT NULL DEFAULT TRUE,
    is_free_hit          BOOLEAN NOT NULL DEFAULT FALSE,
    is_wicket            BOOLEAN NOT NULL DEFAULT FALSE,
    wicket_type          VARCHAR(32),
    dismissed_player_id  INTEGER REFERENCES players (id),
    dismissed_role       VARCHAR(12),
    is_voided            BOOLEAN NOT NULL DEFAULT FALSE,
    voided_at            TIMESTAMPTZ,
    void_reason          VARCHAR(200),
    created_at           TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_deliveries_innings_sequence UNIQUE (innings_id, sequence),
    CONSTRAINT uq_deliveries_innings_client_event UNIQUE (innings_id, client_event_id),
    CONSTRAINT ck_deliveries_runs CHECK (
        runs_off_bat >= 0 AND extra_runs >= 0 AND penalty_runs >= 0 AND total_runs >= 0
    ),
    CONSTRAINT ck_deliveries_position CHECK (over_number >= 1 AND ball_in_over >= 1),
    CONSTRAINT ck_deliveries_extra_type CHECK (
        extra_type IS NULL OR extra_type IN ('wide', 'no_ball', 'bye', 'leg_bye')
    ),
    CONSTRAINT ck_deliveries_dismissed_role CHECK (
        dismissed_role IS NULL OR dismissed_role IN ('striker', 'non_striker')
    )
);
CREATE INDEX ix_deliveries_innings_id ON deliveries (innings_id);

CREATE TABLE match_events (
    id          SERIAL PRIMARY KEY,
    match_id    INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
    innings_id  INTEGER REFERENCES innings (id) ON DELETE SET NULL,
    delivery_id INTEGER REFERENCES deliveries (id) ON DELETE SET NULL,
    event_type  VARCHAR(48) NOT NULL,
    actor       VARCHAR(64) NOT NULL DEFAULT 'scorer',
    payload     JSON,
    created_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_match_events_event_type ON match_events (event_type);
CREATE INDEX ix_match_events_match_id ON match_events (match_id);
CREATE INDEX ix_match_events_match_id_id ON match_events (match_id, id);

CREATE TABLE player_match_statistics (
    id               SERIAL PRIMARY KEY,
    match_id         INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
    player_id        INTEGER NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    team_id          INTEGER NOT NULL REFERENCES teams (id),
    batting_innings  INTEGER NOT NULL DEFAULT 0,
    runs             INTEGER NOT NULL DEFAULT 0,
    highest_score    INTEGER NOT NULL DEFAULT 0,
    balls_faced      INTEGER NOT NULL DEFAULT 0,
    fours            INTEGER NOT NULL DEFAULT 0,
    sixes            INTEGER NOT NULL DEFAULT 0,
    is_out           BOOLEAN NOT NULL DEFAULT FALSE,
    not_outs         INTEGER NOT NULL DEFAULT 0,
    dismissal        VARCHAR(64),
    bowling_innings  INTEGER NOT NULL DEFAULT 0,
    balls_bowled     INTEGER NOT NULL DEFAULT 0,
    runs_conceded    INTEGER NOT NULL DEFAULT 0,
    wickets          INTEGER NOT NULL DEFAULT 0,
    best_bowling_wickets INTEGER NOT NULL DEFAULT 0,
    best_bowling_runs    INTEGER NOT NULL DEFAULT 0,
    fantasy_points   INTEGER NOT NULL DEFAULT 0,
    wides            INTEGER NOT NULL DEFAULT 0,
    no_balls         INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_player_match_statistics UNIQUE (match_id, player_id),
    CONSTRAINT ck_player_match_statistics_values CHECK (
        runs >= 0 AND balls_faced >= 0 AND wickets >= 0 AND runs_conceded >= 0
    )
);
CREATE INDEX ix_player_match_statistics_match_id ON player_match_statistics (match_id);
CREATE INDEX ix_player_match_statistics_player_id ON player_match_statistics (player_id);
CREATE INDEX ix_player_match_statistics_team_id ON player_match_statistics (team_id);

CREATE TABLE retirements (
    id                    SERIAL PRIMARY KEY,
    innings_id            INTEGER NOT NULL REFERENCES innings (id) ON DELETE CASCADE,
    player_id             INTEGER NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    retirement_type       VARCHAR(24) NOT NULL,
    reason                VARCHAR(200),
    replacement_player_id INTEGER REFERENCES players (id),
    retired_after_sequence INTEGER NOT NULL DEFAULT 0,
    retired_at            TIMESTAMPTZ NOT NULL,
    returned_after_sequence INTEGER,
    returned_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_retirements_innings_player_sequence UNIQUE (innings_id, player_id, retired_after_sequence),
    CONSTRAINT ck_retirements_type CHECK (retirement_type IN ('retired_not_out', 'retired_out', 'retired_hurt')),
    CONSTRAINT ck_retirements_sequence CHECK (retired_after_sequence >= 0)
);
CREATE INDEX ix_retirements_innings_id ON retirements (innings_id);
CREATE INDEX ix_retirements_player_id ON retirements (player_id);

CREATE TABLE fantasy_points (
    id          SERIAL PRIMARY KEY,
    match_id    INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
    innings_id  INTEGER REFERENCES innings (id) ON DELETE CASCADE,
    player_id   INTEGER NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    delivery_id INTEGER REFERENCES deliveries (id) ON DELETE SET NULL,
    category    VARCHAR(32) NOT NULL,
    points      INTEGER NOT NULL,
    source_key  VARCHAR(120) NOT NULL,
    detail      VARCHAR(160),
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_fantasy_points_source UNIQUE (match_id, source_key)
);
CREATE INDEX ix_fantasy_points_match_id ON fantasy_points (match_id);
CREATE INDEX ix_fantasy_points_player_id ON fantasy_points (player_id);
