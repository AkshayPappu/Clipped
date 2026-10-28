-- Clipped schema and token-checked RPCs.
-- Run this in the Supabase SQL editor before seed.sql.
-- The Streamlit server calls these functions with the service role key.
-- Anonymous and authenticated roles have no table access and no execute grants.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL CHECK (code ~ '^[0-9]{4}$'),
    status TEXT NOT NULL DEFAULT 'lobby' CHECK (
        status IN ('lobby', 'prompt', 'voting', 'leaderboard', 'final_results', 'expired')
    ),
    host_player_id UUID,
    total_rounds INTEGER NOT NULL DEFAULT 5 CHECK (total_rounds IN (5, 10, 15, 20)),
    answer_seconds INTEGER NOT NULL DEFAULT 60 CHECK (answer_seconds IN (30, 45, 60, 90)),
    vote_seconds INTEGER NOT NULL DEFAULT 45 CHECK (vote_seconds IN (30, 45, 60, 90)),
    categories TEXT[] NOT NULL DEFAULT ARRAY['lore', 'exposing', 'deep_cuts', 'brainrot', 'legendary'],
    question_order TEXT NOT NULL DEFAULT 'random' CHECK (question_order IN ('random', 'sequential')),
    phase_deadline TIMESTAMPTZ,
    current_round INTEGER NOT NULL DEFAULT 0 CHECK (current_round >= 0),
    deck UUID[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp() + INTERVAL '12 hours'
);

CREATE UNIQUE INDEX IF NOT EXISTS rooms_active_code_idx
    ON rooms (code)
    WHERE status <> 'expired';

CREATE INDEX IF NOT EXISTS rooms_expires_idx ON rooms (expires_at);

CREATE TABLE IF NOT EXISTS players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    display_name TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 2 AND 20),
    session_token_hash TEXT NOT NULL UNIQUE,
    is_host BOOLEAN NOT NULL DEFAULT FALSE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    left_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS players_room_name_idx
    ON players (room_id, lower(display_name))
    WHERE left_at IS NULL;

CREATE INDEX IF NOT EXISTS players_room_idx ON players (room_id);
CREATE INDEX IF NOT EXISTS players_token_idx ON players (session_token_hash);

CREATE TABLE IF NOT EXISTS player_actions (
    player_id UUID NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    acted_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (player_id, action)
);

CREATE TABLE IF NOT EXISTS prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category TEXT NOT NULL CHECK (
        category IN ('lore', 'exposing', 'deep_cuts', 'brainrot', 'legendary', 'custom')
    ),
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 10 AND 240),
    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
    sort_index INTEGER NOT NULL DEFAULT 0,
    owner_room_id UUID REFERENCES rooms (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE UNIQUE INDEX IF NOT EXISTS prompts_builtin_body_idx
    ON prompts (body)
    WHERE is_builtin;

CREATE INDEX IF NOT EXISTS prompts_category_idx ON prompts (category);
CREATE INDEX IF NOT EXISTS prompts_owner_idx ON prompts (owner_room_id);

CREATE TABLE IF NOT EXISTS room_prompts (
    room_id UUID NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    prompt_id UUID NOT NULL REFERENCES prompts (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    included BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (room_id, prompt_id)
);

CREATE TABLE IF NOT EXISTS rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL CHECK (round_number > 0),
    prompt_id UUID REFERENCES prompts (id),
    question_body TEXT NOT NULL,
    category TEXT NOT NULL,
    finalized BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (room_id, round_number)
);

CREATE INDEX IF NOT EXISTS rounds_room_idx ON rounds (room_id);

CREATE TABLE IF NOT EXISTS answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id UUID NOT NULL REFERENCES rounds (id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 280),
    display_order INTEGER NOT NULL DEFAULT 0,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (round_id, player_id)
);

CREATE INDEX IF NOT EXISTS answers_round_idx ON answers (round_id);

CREATE TABLE IF NOT EXISTS votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    answer_id UUID NOT NULL REFERENCES answers (id) ON DELETE CASCADE,
    voter_id UUID NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    verdict TEXT NOT NULL CHECK (verdict IN ('gem', 'common', 'fake')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (answer_id, voter_id)
);

CREATE INDEX IF NOT EXISTS votes_answer_idx ON votes (answer_id);

CREATE TABLE IF NOT EXISTS round_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id UUID NOT NULL REFERENCES rounds (id) ON DELETE CASCADE,
    answer_id UUID NOT NULL REFERENCES answers (id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    gem_count INTEGER NOT NULL CHECK (gem_count >= 0),
    common_count INTEGER NOT NULL CHECK (common_count >= 0),
    fake_count INTEGER NOT NULL CHECK (fake_count >= 0),
    winning_verdict TEXT NOT NULL CHECK (winning_verdict IN ('gem', 'common', 'fake', 'none')),
    points_awarded INTEGER NOT NULL CHECK (points_awarded IN (0, 100, 300)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (round_id, answer_id),
    UNIQUE (round_id, player_id)
);

CREATE INDEX IF NOT EXISTS round_results_round_idx ON round_results (round_id);
CREATE INDEX IF NOT EXISTS round_results_player_idx ON round_results (player_id);

-- Host link is intentionally not a foreign key. A room delete cascades to
-- players, and a host FK back to players deadlocks that cascade.

ALTER TABLE rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE players ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompts ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_prompts ENABLE ROW LEVEL SECURITY;
ALTER TABLE rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE round_results ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION _fail(p_message TEXT)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT jsonb_build_object('ok', false, 'error', p_message);
$$;

CREATE OR REPLACE FUNCTION _iso(p_ts TIMESTAMPTZ)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT to_char(p_ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"');
$$;

CREATE OR REPLACE FUNCTION _hash_token(p_token TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT encode(digest(convert_to(p_token, 'UTF8'), 'sha256'), 'hex');
$$;

CREATE OR REPLACE FUNCTION _clean_name(p_name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_name TEXT := btrim(regexp_replace(coalesce(p_name, ''), '\s+', ' ', 'g'));
BEGIN
    IF v_name IS NULL OR char_length(v_name) < 2 OR char_length(v_name) > 20 THEN
        RETURN NULL;
    END IF;
    IF v_name ~ '[[:cntrl:]]' THEN
        RETURN NULL;
    END IF;
    RETURN v_name;
END;
$$;

CREATE OR REPLACE FUNCTION _consensus(p_gem INTEGER, p_common INTEGER, p_fake INTEGER)
RETURNS TABLE(verdict TEXT, points INTEGER)
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_best INTEGER;
BEGIN
    IF coalesce(p_gem, 0) + coalesce(p_common, 0) + coalesce(p_fake, 0) = 0 THEN
        verdict := 'none';
        points := 0;
        RETURN NEXT;
        RETURN;
    END IF;
    v_best := GREATEST(p_gem, p_common, p_fake);
    IF p_fake = v_best THEN
        verdict := 'fake';
        points := 0;
    ELSIF p_common = v_best THEN
        verdict := 'common';
        points := 100;
    ELSE
        verdict := 'gem';
        points := 300;
    END IF;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION _reject_self_vote()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_author UUID;
BEGIN
    SELECT player_id INTO v_author FROM answers WHERE id = NEW.answer_id;
    IF v_author = NEW.voter_id THEN
        RAISE EXCEPTION 'self_vote' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS votes_reject_self ON votes;
CREATE TRIGGER votes_reject_self
    BEFORE INSERT OR UPDATE ON votes
    FOR EACH ROW
    EXECUTE FUNCTION _reject_self_vote();

CREATE OR REPLACE FUNCTION _throttle(p_player_id UUID, p_action TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_prev TIMESTAMPTZ;
BEGIN
    SELECT acted_at INTO v_prev
    FROM player_actions
    WHERE player_id = p_player_id AND action = p_action
    FOR UPDATE;
    IF v_prev IS NOT NULL AND clock_timestamp() - v_prev < INTERVAL '300 milliseconds' THEN
        RETURN _fail('Slow down a second.');
    END IF;
    INSERT INTO player_actions (player_id, action, acted_at)
    VALUES (p_player_id, p_action, clock_timestamp())
    ON CONFLICT (player_id, action) DO UPDATE SET acted_at = clock_timestamp();
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION _lock_player(p_token TEXT)
RETURNS TABLE(err JSONB, player_id UUID, room_id UUID, is_host BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_player players%ROWTYPE;
    v_room rooms%ROWTYPE;
BEGIN
    IF p_token IS NULL OR char_length(p_token) < 16 THEN
        err := _fail('Session expired. Join again.');
        RETURN NEXT;
        RETURN;
    END IF;
    SELECT * INTO v_player
    FROM players
    WHERE session_token_hash = _hash_token(p_token);
    IF NOT FOUND OR v_player.left_at IS NOT NULL THEN
        err := _fail('Session expired. Join again.');
        RETURN NEXT;
        RETURN;
    END IF;
    SELECT * INTO v_room FROM rooms WHERE id = v_player.room_id FOR UPDATE;
    SELECT * INTO v_player FROM players WHERE id = v_player.id FOR UPDATE;
    IF v_room.status = 'expired' OR v_room.expires_at <= clock_timestamp() THEN
        UPDATE rooms SET status = 'expired' WHERE id = v_room.id;
        err := _fail('This room expired.');
        RETURN NEXT;
        RETURN;
    END IF;
    UPDATE players SET last_seen = clock_timestamp() WHERE id = v_player.id;
    err := NULL;
    player_id := v_player.id;
    room_id := v_room.id;
    is_host := v_player.is_host;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION _finalize_round(p_round_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO round_results (
        round_id, answer_id, player_id, gem_count, common_count, fake_count, winning_verdict, points_awarded
    )
    SELECT
        a.round_id,
        a.id,
        a.player_id,
        coalesce(t.gem, 0),
        coalesce(t.common, 0),
        coalesce(t.fake, 0),
        c.verdict,
        c.points
    FROM answers a
    LEFT JOIN (
        SELECT
            answer_id,
            count(*) FILTER (WHERE verdict = 'gem')::INTEGER AS gem,
            count(*) FILTER (WHERE verdict = 'common')::INTEGER AS common,
            count(*) FILTER (WHERE verdict = 'fake')::INTEGER AS fake
        FROM votes
        GROUP BY answer_id
    ) t ON t.answer_id = a.id
    CROSS JOIN LATERAL _consensus(
        coalesce(t.gem, 0),
        coalesce(t.common, 0),
        coalesce(t.fake, 0)
    ) c
    WHERE a.round_id = p_round_id
    ON CONFLICT (round_id, answer_id) DO NOTHING;

    UPDATE rounds SET finalized = TRUE WHERE id = p_round_id AND NOT finalized;
END;
$$;

CREATE OR REPLACE FUNCTION _maybe_advance(p_room_id UUID, p_force BOOLEAN)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_room rooms%ROWTYPE;
    v_round rounds%ROWTYPE;
    v_active INTEGER;
    v_submitted INTEGER;
    v_needed INTEGER;
    v_cast INTEGER;
    v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
    SELECT * INTO v_room FROM rooms WHERE id = p_room_id FOR UPDATE;
    IF v_room.status = 'prompt' THEN
        SELECT * INTO v_round
        FROM rounds
        WHERE room_id = v_room.id AND round_number = v_room.current_round
        FOR UPDATE;
        IF NOT FOUND THEN
            RETURN;
        END IF;
        SELECT count(*) INTO v_active FROM players WHERE room_id = v_room.id AND left_at IS NULL;
        SELECT count(*) INTO v_submitted FROM answers WHERE round_id = v_round.id;
        IF p_force OR v_submitted >= v_active OR (v_room.phase_deadline IS NOT NULL AND v_room.phase_deadline <= v_now) THEN
            IF v_submitted = 0 THEN
                UPDATE rounds SET finalized = TRUE WHERE id = v_round.id;
                UPDATE rooms SET status = 'leaderboard', phase_deadline = NULL WHERE id = v_room.id;
            ELSE
                UPDATE answers a
                SET display_order = s.ord
                FROM (
                    SELECT id, (row_number() OVER (ORDER BY random())) - 1 AS ord
                    FROM answers
                    WHERE round_id = v_round.id
                ) s
                WHERE a.id = s.id;
                UPDATE rooms
                SET status = 'voting',
                    phase_deadline = v_now + make_interval(secs => v_room.vote_seconds)
                WHERE id = v_room.id;
            END IF;
        END IF;
    ELSIF v_room.status = 'voting' THEN
        SELECT * INTO v_round
        FROM rounds
        WHERE room_id = v_room.id AND round_number = v_room.current_round
        FOR UPDATE;
        IF NOT FOUND THEN
            RETURN;
        END IF;
        SELECT count(*) INTO v_needed
        FROM answers a
        JOIN players p ON p.room_id = v_room.id AND p.left_at IS NULL AND p.id <> a.player_id
        WHERE a.round_id = v_round.id;
        SELECT count(*) INTO v_cast
        FROM votes v
        JOIN answers a ON a.id = v.answer_id AND a.round_id = v_round.id
        JOIN players p ON p.id = v.voter_id AND p.left_at IS NULL AND p.room_id = v_room.id
        WHERE v.voter_id <> a.player_id;
        IF p_force OR v_cast >= v_needed OR (v_room.phase_deadline IS NOT NULL AND v_room.phase_deadline <= v_now) THEN
            PERFORM _finalize_round(v_round.id);
            UPDATE rooms SET status = 'leaderboard', phase_deadline = NULL WHERE id = v_room.id;
        END IF;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION _catch_up(p_room_id UUID, p_force BOOLEAN)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_before TEXT;
    v_after TEXT;
    v_force BOOLEAN := p_force;
    i INTEGER;
BEGIN
    FOR i IN 1..3 LOOP
        SELECT status || ':' || current_round::TEXT || ':' || coalesce(phase_deadline::TEXT, '')
        INTO v_before
        FROM rooms WHERE id = p_room_id;
        PERFORM _maybe_advance(p_room_id, v_force);
        v_force := FALSE;
        SELECT status || ':' || current_round::TEXT || ':' || coalesce(phase_deadline::TEXT, '')
        INTO v_after
        FROM rooms WHERE id = p_room_id;
        EXIT WHEN v_before = v_after;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION _leaderboard_standings(p_room_id UUID, p_round_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    WITH base AS (
        SELECT
            p.id,
            p.display_name,
            coalesce(sum(rr.points_awarded), 0)::INTEGER AS points,
            coalesce(sum(rr.points_awarded) FILTER (WHERE rr.round_id = p_round_id), 0)::INTEGER AS round_points,
            coalesce(count(*) FILTER (WHERE rr.winning_verdict = 'gem'), 0)::INTEGER AS gems,
            coalesce(sum(rr.points_awarded) FILTER (WHERE p_round_id IS NULL OR rr.round_id <> p_round_id), 0)::INTEGER AS prev_points,
            coalesce(count(*) FILTER (
                WHERE rr.winning_verdict = 'gem' AND (p_round_id IS NULL OR rr.round_id <> p_round_id)
            ), 0)::INTEGER AS prev_gems
        FROM players p
        LEFT JOIN round_results rr
            ON rr.player_id = p.id
           AND rr.round_id IN (SELECT id FROM rounds WHERE room_id = p_room_id)
        WHERE p.room_id = p_room_id AND p.left_at IS NULL
        GROUP BY p.id, p.display_name
    ),
    ranked AS (
        SELECT
            *,
            row_number() OVER (ORDER BY points DESC, gems DESC, lower(display_name)) AS rank,
            row_number() OVER (ORDER BY prev_points DESC, prev_gems DESC, lower(display_name)) AS prev_rank
        FROM base
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'rank', rank,
        'display_name', display_name,
        'points', points,
        'gems', gems,
        'delta', prev_rank - rank,
        'round_points', round_points
    ) ORDER BY rank), '[]'::JSONB)
    FROM ranked;
$$;

CREATE OR REPLACE FUNCTION _build_view(p_player_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_player players%ROWTYPE;
    v_room rooms%ROWTYPE;
    v_round rounds%ROWTYPE;
    v_players JSONB;
    v_prompt JSONB;
    v_voting JSONB;
    v_board JSONB;
    v_final JSONB;
    v_custom JSONB := '[]'::JSONB;
    v_deck_count INTEGER := 0;
    v_standings JSONB;
    v_reveals JSONB;
    v_best JSONB;
    v_winners JSONB;
    v_top INTEGER;
    v_gems INTEGER;
    v_fakes INTEGER;
    v_total INTEGER;
BEGIN
    SELECT * INTO v_player FROM players WHERE id = p_player_id;
    SELECT * INTO v_room FROM rooms WHERE id = v_player.room_id;
    SELECT * INTO v_round
    FROM rounds
    WHERE room_id = v_room.id AND round_number = v_room.current_round;

    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', p.id,
        'display_name', p.display_name,
        'is_host', p.is_host,
        'is_away', EXTRACT(EPOCH FROM (clock_timestamp() - p.last_seen)) > 45,
        'joined_at', _iso(p.joined_at)
    ) ORDER BY p.joined_at), '[]'::JSONB)
    INTO v_players
    FROM players p
    WHERE p.room_id = v_room.id AND p.left_at IS NULL;

    IF v_room.status = 'lobby' THEN
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'id', p.id,
            'body', p.body,
            'included', rp.included
        ) ORDER BY p.created_at), '[]'::JSONB)
        INTO v_custom
        FROM prompts p
        JOIN room_prompts rp ON rp.prompt_id = p.id AND rp.room_id = v_room.id
        WHERE p.is_builtin = FALSE AND p.owner_room_id = v_room.id;

        SELECT
            (SELECT count(*) FROM prompts WHERE is_builtin AND category = ANY (v_room.categories))
            +
            (SELECT count(*)
             FROM prompts p
             JOIN room_prompts rp ON rp.prompt_id = p.id AND rp.room_id = v_room.id AND rp.included
             WHERE p.is_builtin = FALSE AND p.owner_room_id = v_room.id)
        INTO v_deck_count;
    ELSIF v_room.status = 'prompt' AND v_round.id IS NOT NULL THEN
        SELECT jsonb_build_object(
            'round_number', v_round.round_number,
            'total_rounds', v_room.total_rounds,
            'question', v_round.question_body,
            'category', v_round.category,
            'submitted_count', (SELECT count(*) FROM answers a WHERE a.round_id = v_round.id),
            'player_count', (SELECT count(*) FROM players p WHERE p.room_id = v_room.id AND p.left_at IS NULL),
            'your_answer', (SELECT a.body FROM answers a WHERE a.round_id = v_round.id AND a.player_id = v_player.id),
            'deadline', _iso(v_room.phase_deadline)
        ) INTO v_prompt;
    ELSIF v_room.status = 'voting' AND v_round.id IS NOT NULL THEN
        SELECT jsonb_build_object(
            'round_number', v_round.round_number,
            'total_rounds', v_room.total_rounds,
            'question', v_round.question_body,
            'category', v_round.category,
            'deadline', _iso(v_room.phase_deadline),
            'votes_needed', (
                SELECT count(*)
                FROM answers a
                JOIN players p ON p.room_id = v_room.id AND p.left_at IS NULL AND p.id <> a.player_id
                WHERE a.round_id = v_round.id
            ),
            'votes_cast', (
                SELECT count(*)
                FROM votes v
                JOIN answers a ON a.id = v.answer_id AND a.round_id = v_round.id
                JOIN players p ON p.id = v.voter_id AND p.left_at IS NULL
                WHERE v.voter_id <> a.player_id
            ),
            'answers', coalesce((
                SELECT jsonb_agg(jsonb_build_object(
                    'id', a.id,
                    'body', a.body,
                    'is_own', a.player_id = v_player.id,
                    'your_vote', (
                        SELECT v.verdict FROM votes v
                        WHERE v.answer_id = a.id AND v.voter_id = v_player.id
                    )
                ) ORDER BY a.display_order, a.submitted_at)
                FROM answers a
                WHERE a.round_id = v_round.id
            ), '[]'::JSONB)
        ) INTO v_voting;
    ELSIF v_room.status = 'leaderboard' AND v_round.id IS NOT NULL THEN
        v_standings := _leaderboard_standings(v_room.id, v_round.id);
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'body', a.body,
            'author', pl.display_name,
            'verdict', rr.winning_verdict,
            'points', rr.points_awarded,
            'gem', rr.gem_count,
            'common', rr.common_count,
            'fake', rr.fake_count
        ) ORDER BY rr.points_awarded DESC, rr.gem_count DESC, a.display_order), '[]'::JSONB)
        INTO v_reveals
        FROM round_results rr
        JOIN answers a ON a.id = rr.answer_id
        JOIN players pl ON pl.id = rr.player_id
        WHERE rr.round_id = v_round.id;
        v_board := jsonb_build_object(
            'round_number', v_round.round_number,
            'total_rounds', v_room.total_rounds,
            'is_final_round', v_room.current_round >= v_room.total_rounds,
            'question', v_round.question_body,
            'category', v_round.category,
            'reveals', v_reveals,
            'standings', v_standings
        );
    ELSIF v_room.status = 'final_results' THEN
        v_standings := _leaderboard_standings(v_room.id, NULL);
        SELECT coalesce(max((item->>'points')::INTEGER), 0) INTO v_top
        FROM jsonb_array_elements(v_standings) item;
        SELECT coalesce(jsonb_agg(item->>'display_name' ORDER BY (item->>'rank')::INTEGER), '[]'::JSONB)
        INTO v_winners
        FROM jsonb_array_elements(v_standings) item
        WHERE (item->>'points')::INTEGER = v_top;
        SELECT jsonb_build_object(
            'body', a.body,
            'author', pl.display_name,
            'points', rr.points_awarded,
            'verdict', rr.winning_verdict
        )
        INTO v_best
        FROM round_results rr
        JOIN answers a ON a.id = rr.answer_id
        JOIN players pl ON pl.id = rr.player_id
        JOIN rounds rd ON rd.id = rr.round_id
        WHERE rd.room_id = v_room.id
        ORDER BY rr.points_awarded DESC, rr.gem_count DESC, a.submitted_at ASC, a.body ASC
        LIMIT 1;
        SELECT
            count(*) FILTER (WHERE rr.winning_verdict = 'gem'),
            count(*) FILTER (WHERE rr.winning_verdict = 'fake'),
            count(*)
        INTO v_gems, v_fakes, v_total
        FROM round_results rr
        JOIN rounds rd ON rd.id = rr.round_id
        WHERE rd.room_id = v_room.id;
        v_final := jsonb_build_object(
            'winners', v_winners,
            'tied', jsonb_array_length(v_winners) > 1,
            'standings', v_standings,
            'best_answer', v_best,
            'fake_news_count', coalesce(v_fakes, 0),
            'gem_count', coalesce(v_gems, 0),
            'total_answers', coalesce(v_total, 0)
        );
    END IF;

    RETURN jsonb_build_object(
        'ok', true,
        'local_mode', false,
        'server_now', _iso(clock_timestamp()),
        'room', jsonb_build_object(
            'id', v_room.id,
            'code', v_room.code,
            'status', v_room.status,
            'phase_deadline', _iso(v_room.phase_deadline),
            'current_round', v_room.current_round,
            'total_rounds', v_room.total_rounds,
            'answer_seconds', v_room.answer_seconds,
            'vote_seconds', v_room.vote_seconds,
            'categories', to_jsonb(v_room.categories),
            'question_order', v_room.question_order,
            'player_count', (SELECT count(*) FROM players p WHERE p.room_id = v_room.id AND p.left_at IS NULL),
            'max_players', 12,
            'expires_at', _iso(v_room.expires_at)
        ),
        'you', jsonb_build_object(
            'id', v_player.id,
            'display_name', v_player.display_name,
            'is_host', v_player.is_host
        ),
        'players', v_players,
        'prompt', v_prompt,
        'voting', v_voting,
        'leaderboard', v_board,
        'final', v_final,
        'custom_prompts', v_custom,
        'deck_count', v_deck_count
    );
END;
$$;

-- ---------------------------------------------------------------------------
-- Public RPCs
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION create_room(p_display_name TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_name TEXT := _clean_name(p_display_name);
    v_code TEXT;
    v_room_id UUID;
    v_player_id UUID;
    v_token TEXT;
    v_try INTEGER;
BEGIN
    IF v_name IS NULL THEN
        RETURN _fail('Use 2–20 characters.');
    END IF;
    FOR v_try IN 1..50 LOOP
        v_code := lpad((floor(random() * 10000))::INTEGER::TEXT, 4, '0');
        BEGIN
            INSERT INTO rooms (code, status, categories, question_order, expires_at)
            VALUES (
                v_code,
                'lobby',
                ARRAY['lore', 'exposing', 'deep_cuts', 'brainrot', 'legendary'],
                'random',
                clock_timestamp() + INTERVAL '12 hours'
            )
            RETURNING id INTO v_room_id;
            EXIT;
        EXCEPTION WHEN unique_violation THEN
            v_room_id := NULL;
        END;
    END LOOP;
    IF v_room_id IS NULL THEN
        RETURN _fail('Couldn''t mint a room code. Try again.');
    END IF;
    v_token := encode(gen_random_bytes(32), 'hex');
    INSERT INTO players (room_id, display_name, session_token_hash, is_host)
    VALUES (v_room_id, v_name, _hash_token(v_token), TRUE)
    RETURNING id INTO v_player_id;
    UPDATE rooms SET host_player_id = v_player_id WHERE id = v_room_id;
    RETURN _build_view(v_player_id) || jsonb_build_object('token', v_token);
END;
$$;

CREATE OR REPLACE FUNCTION join_room(p_code TEXT, p_display_name TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_name TEXT := _clean_name(p_display_name);
    v_code TEXT := btrim(coalesce(p_code, ''));
    v_room rooms%ROWTYPE;
    v_token TEXT;
    v_player_id UUID;
    v_count INTEGER;
BEGIN
    IF v_name IS NULL THEN
        RETURN _fail('Use 2–20 characters.');
    END IF;
    IF v_code !~ '^[0-9]{4}$' THEN
        RETURN _fail('Enter a four-digit code.');
    END IF;
    SELECT * INTO v_room
    FROM rooms
    WHERE code = v_code AND status <> 'expired'
    ORDER BY created_at DESC
    LIMIT 1
    FOR UPDATE;
    IF NOT FOUND THEN
        IF EXISTS (SELECT 1 FROM rooms WHERE code = v_code) THEN
            RETURN _fail('This room expired.');
        END IF;
        RETURN _fail('That room doesn''t exist.');
    END IF;
    IF v_room.expires_at <= clock_timestamp() THEN
        UPDATE rooms SET status = 'expired' WHERE id = v_room.id;
        RETURN _fail('This room expired.');
    END IF;
    IF v_room.status <> 'lobby' THEN
        RETURN _fail('This game already started.');
    END IF;
    SELECT count(*) INTO v_count FROM players WHERE room_id = v_room.id AND left_at IS NULL;
    IF v_count >= 12 THEN
        RETURN _fail('Room''s full.');
    END IF;
    IF EXISTS (
        SELECT 1 FROM players
        WHERE room_id = v_room.id AND left_at IS NULL AND lower(display_name) = lower(v_name)
    ) THEN
        RETURN _fail('That name''s taken. Pick another.');
    END IF;
    v_token := encode(gen_random_bytes(32), 'hex');
    BEGIN
        INSERT INTO players (room_id, display_name, session_token_hash, is_host)
        VALUES (v_room.id, v_name, _hash_token(v_token), FALSE)
        RETURNING id INTO v_player_id;
    EXCEPTION WHEN unique_violation THEN
        RETURN _fail('That name''s taken. Pick another.');
    END;
    RETURN _build_view(v_player_id) || jsonb_build_object('token', v_token);
END;
$$;

CREATE OR REPLACE FUNCTION reconnect(p_token TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    PERFORM _catch_up(v_room_id, FALSE);
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION leave_room(p_token TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_next UUID;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    UPDATE players
    SET left_at = clock_timestamp(), is_host = FALSE
    WHERE id = v_player_id;
    IF v_is_host THEN
        SELECT id INTO v_next
        FROM players
        WHERE room_id = v_room_id AND left_at IS NULL
        ORDER BY joined_at
        LIMIT 1;
        IF v_next IS NOT NULL THEN
            UPDATE players SET is_host = TRUE WHERE id = v_next;
            UPDATE rooms SET host_player_id = v_next WHERE id = v_room_id;
        ELSE
            UPDATE rooms SET status = 'expired' WHERE id = v_room_id;
        END IF;
    END IF;
    RETURN jsonb_build_object('ok', true);
END;
$$;

CREATE OR REPLACE FUNCTION update_settings(
    p_token TEXT,
    p_total_rounds INTEGER,
    p_answer_seconds INTEGER,
    p_vote_seconds INTEGER,
    p_categories TEXT[],
    p_question_order TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_cat TEXT;
    v_clean TEXT[] := ARRAY[]::TEXT[];
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id;
    IF v_room.status <> 'lobby' THEN
        RETURN _fail('You can''t change that mid-game.');
    END IF;
    IF p_total_rounds NOT IN (5, 10, 15, 20)
        OR p_answer_seconds NOT IN (30, 45, 60, 90)
        OR p_vote_seconds NOT IN (30, 45, 60, 90)
        OR p_question_order NOT IN ('random', 'sequential') THEN
        RETURN _fail('Those settings don''t work. Check rounds, timers, and categories.');
    END IF;
    IF p_categories IS NULL THEN
        RETURN _fail('Pick a real category.');
    END IF;
    FOREACH v_cat IN ARRAY p_categories LOOP
        IF v_cat NOT IN ('lore', 'exposing', 'deep_cuts', 'brainrot', 'legendary') THEN
            RETURN _fail('Pick a real category.');
        END IF;
        IF NOT v_cat = ANY (v_clean) THEN
            v_clean := array_append(v_clean, v_cat);
        END IF;
    END LOOP;
    v_throttled := _throttle(v_player_id, 'update_settings');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    UPDATE rooms
    SET total_rounds = p_total_rounds,
        answer_seconds = p_answer_seconds,
        vote_seconds = p_vote_seconds,
        categories = v_clean,
        question_order = p_question_order
    WHERE id = v_room_id;
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION save_custom_prompt(p_token TEXT, p_body TEXT, p_prompt_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_body TEXT := btrim(regexp_replace(coalesce(p_body, ''), '\s+', ' ', 'g'));
    v_prompt prompts%ROWTYPE;
    v_id UUID;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id;
    IF v_room.status <> 'lobby' THEN
        RETURN _fail('You can''t change that mid-game.');
    END IF;
    IF v_body IS NULL OR char_length(v_body) < 10 OR char_length(v_body) > 240 OR v_body ~ '[[:cntrl:]]' THEN
        RETURN _fail('Questions need 10–240 characters.');
    END IF;
    v_throttled := _throttle(v_player_id, 'save_custom_prompt');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    IF p_prompt_id IS NOT NULL THEN
        SELECT * INTO v_prompt FROM prompts WHERE id = p_prompt_id;
        IF NOT FOUND OR v_prompt.is_builtin OR v_prompt.owner_room_id IS DISTINCT FROM v_room_id THEN
            RETURN _fail('Questions need 10–240 characters.');
        END IF;
        UPDATE prompts SET body = v_body WHERE id = p_prompt_id;
    ELSE
        INSERT INTO prompts (category, body, is_builtin, sort_index, owner_room_id)
        VALUES (
            'custom',
            v_body,
            FALSE,
            coalesce((SELECT max(sort_index) + 1 FROM prompts), 1),
            v_room_id
        )
        RETURNING id INTO v_id;
        INSERT INTO room_prompts (room_id, prompt_id, position, included)
        VALUES (v_room_id, v_id, 0, TRUE);
    END IF;
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION delete_custom_prompt(p_token TEXT, p_prompt_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_prompt prompts%ROWTYPE;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id;
    IF v_room.status <> 'lobby' THEN
        RETURN _fail('You can''t change that mid-game.');
    END IF;
    SELECT * INTO v_prompt FROM prompts WHERE id = p_prompt_id;
    IF NOT FOUND OR v_prompt.is_builtin OR v_prompt.owner_room_id IS DISTINCT FROM v_room_id THEN
        RETURN _fail('Questions need 10–240 characters.');
    END IF;
    v_throttled := _throttle(v_player_id, 'delete_custom_prompt');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    DELETE FROM prompts WHERE id = p_prompt_id;
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION set_prompt_included(p_token TEXT, p_prompt_id UUID, p_included BOOLEAN)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_prompt prompts%ROWTYPE;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id;
    IF v_room.status <> 'lobby' THEN
        RETURN _fail('You can''t change that mid-game.');
    END IF;
    SELECT * INTO v_prompt FROM prompts WHERE id = p_prompt_id;
    IF NOT FOUND OR v_prompt.is_builtin OR v_prompt.owner_room_id IS DISTINCT FROM v_room_id THEN
        RETURN _fail('Questions need 10–240 characters.');
    END IF;
    v_throttled := _throttle(v_player_id, 'set_prompt_included');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    UPDATE room_prompts
    SET included = coalesce(p_included, FALSE)
    WHERE room_id = v_room_id AND prompt_id = p_prompt_id;
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION import_prompts(p_token TEXT, p_raw TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_throttled JSONB;
    v_line TEXT;
    v_body TEXT;
    v_added INTEGER := 0;
    v_skipped INTEGER := 0;
    v_id UUID;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id;
    IF v_room.status <> 'lobby' THEN
        RETURN _fail('You can''t change that mid-game.');
    END IF;
    v_throttled := _throttle(v_player_id, 'import_prompts');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    FOR v_line IN SELECT unnest(string_to_array(coalesce(p_raw, ''), E'\n')) LOOP
        IF v_added >= 40 THEN
            IF btrim(v_line) <> '' THEN
                v_skipped := v_skipped + 1;
            END IF;
            CONTINUE;
        END IF;
        v_body := btrim(regexp_replace(coalesce(v_line, ''), '\s+', ' ', 'g'));
        IF v_body = '' THEN
            CONTINUE;
        END IF;
        IF char_length(v_body) < 10 OR char_length(v_body) > 240 OR v_body ~ '[[:cntrl:]]' THEN
            v_skipped := v_skipped + 1;
            CONTINUE;
        END IF;
        IF EXISTS (
            SELECT 1 FROM prompts
            WHERE (is_builtin OR owner_room_id = v_room_id) AND lower(body) = lower(v_body)
        ) THEN
            v_skipped := v_skipped + 1;
            CONTINUE;
        END IF;
        INSERT INTO prompts (category, body, is_builtin, sort_index, owner_room_id)
        VALUES ('custom', v_body, FALSE, coalesce((SELECT max(sort_index) + 1 FROM prompts), 1), v_room_id)
        RETURNING id INTO v_id;
        INSERT INTO room_prompts (room_id, prompt_id, included)
        VALUES (v_room_id, v_id, TRUE);
        v_added := v_added + 1;
    END LOOP;
    RETURN _build_view(v_player_id) || jsonb_build_object('added', v_added, 'skipped', v_skipped);
END;
$$;

CREATE OR REPLACE FUNCTION start_game(p_token TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_count INTEGER;
    v_deck UUID[];
    v_prompt prompts%ROWTYPE;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id FOR UPDATE;
    IF v_room.status <> 'lobby' THEN
        RETURN _build_view(v_player_id);
    END IF;
    SELECT count(*) INTO v_count FROM players WHERE room_id = v_room_id AND left_at IS NULL;
    IF v_count < 2 THEN
        RETURN _fail('Need at least two players.');
    END IF;
    WITH pool AS (
        SELECT p.id, p.category, p.body, p.sort_index
        FROM prompts p
        WHERE p.is_builtin AND p.category = ANY (v_room.categories)
        UNION ALL
        SELECT p.id, p.category, p.body, p.sort_index
        FROM prompts p
        JOIN room_prompts rp ON rp.prompt_id = p.id AND rp.room_id = v_room_id AND rp.included
        WHERE p.is_builtin = FALSE AND p.owner_room_id = v_room_id
    ),
    numbered AS (
        SELECT
            id,
            row_number() OVER (
                ORDER BY
                    CASE WHEN v_room.question_order = 'sequential' THEN
                        CASE category
                            WHEN 'lore' THEN 0
                            WHEN 'exposing' THEN 1
                            WHEN 'deep_cuts' THEN 2
                            WHEN 'brainrot' THEN 3
                            WHEN 'legendary' THEN 4
                            ELSE 5
                        END
                    END,
                    CASE WHEN v_room.question_order = 'sequential' THEN sort_index END,
                    CASE WHEN v_room.question_order = 'sequential' THEN body END,
                    random()
            ) AS ord
        FROM pool
    )
    SELECT coalesce(array_agg(id ORDER BY ord), '{}'::UUID[])
    INTO v_deck
    FROM numbered
    WHERE ord <= v_room.total_rounds;

    IF v_deck IS NULL OR cardinality(v_deck) < v_room.total_rounds THEN
        RETURN _fail('Not enough questions for that many rounds.');
    END IF;
    v_throttled := _throttle(v_player_id, 'start_game');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    SELECT * INTO v_prompt FROM prompts WHERE id = v_deck[1];
    INSERT INTO rounds (room_id, round_number, prompt_id, question_body, category)
    VALUES (v_room_id, 1, v_prompt.id, v_prompt.body, v_prompt.category);
    INSERT INTO room_prompts (room_id, prompt_id, position, included)
    SELECT v_room_id, deck_id, ord::INTEGER, TRUE
    FROM unnest(v_deck) WITH ORDINALITY AS dealt(deck_id, ord)
    ON CONFLICT (room_id, prompt_id) DO UPDATE
    SET position = EXCLUDED.position, included = TRUE;
    UPDATE rooms
    SET status = 'prompt',
        current_round = 1,
        deck = v_deck,
        phase_deadline = clock_timestamp() + make_interval(secs => v_room.answer_seconds)
    WHERE id = v_room_id;
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION submit_answer(p_token TEXT, p_body TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_round rounds%ROWTYPE;
    v_body TEXT := btrim(coalesce(p_body, ''));
    v_existing TEXT;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    PERFORM _catch_up(v_room_id, FALSE);
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id;
    IF v_room.status <> 'prompt' THEN
        RETURN _fail('Time''s up.');
    END IF;
    IF v_body = '' OR v_body ~ '[[:cntrl:]]' THEN
        RETURN _fail('Drop an answer first.');
    END IF;
    IF char_length(v_body) > 280 THEN
        RETURN _fail('Keep it under 280 characters.');
    END IF;
    SELECT * INTO v_round
    FROM rounds
    WHERE room_id = v_room_id AND round_number = v_room.current_round;
    SELECT body INTO v_existing
    FROM answers
    WHERE round_id = v_round.id AND player_id = v_player_id;
    IF FOUND THEN
        IF v_existing = v_body THEN
            RETURN _build_view(v_player_id);
        END IF;
        RETURN _fail('Already locked in.');
    END IF;
    v_throttled := _throttle(v_player_id, 'submit_answer');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    BEGIN
        INSERT INTO answers (round_id, player_id, body)
        VALUES (v_round.id, v_player_id, v_body);
    EXCEPTION WHEN unique_violation THEN
        SELECT body INTO v_existing
        FROM answers
        WHERE round_id = v_round.id AND player_id = v_player_id;
        IF v_existing = v_body THEN
            RETURN _build_view(v_player_id);
        END IF;
        RETURN _fail('Already locked in.');
    END;
    PERFORM _catch_up(v_room_id, FALSE);
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION submit_vote(p_token TEXT, p_answer_id UUID, p_verdict TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_round rounds%ROWTYPE;
    v_answer answers%ROWTYPE;
    v_existing TEXT;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    PERFORM _catch_up(v_room_id, FALSE);
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id;
    IF v_room.status <> 'voting' THEN
        RETURN _fail('Time''s up.');
    END IF;
    IF p_verdict NOT IN ('gem', 'common', 'fake') THEN
        RETURN _fail('That vote doesn''t count.');
    END IF;
    SELECT * INTO v_round
    FROM rounds
    WHERE room_id = v_room_id AND round_number = v_room.current_round;
    SELECT * INTO v_answer FROM answers WHERE id = p_answer_id;
    IF NOT FOUND OR v_answer.round_id <> v_round.id THEN
        RETURN _fail('That vote doesn''t count.');
    END IF;
    IF v_answer.player_id = v_player_id THEN
        RETURN _fail('You can''t vote on your own answer.');
    END IF;
    SELECT verdict INTO v_existing
    FROM votes
    WHERE answer_id = p_answer_id AND voter_id = v_player_id;
    IF FOUND THEN
        IF v_existing = p_verdict THEN
            RETURN _build_view(v_player_id);
        END IF;
        RETURN _fail('You already voted on that.');
    END IF;
    v_throttled := _throttle(v_player_id, 'submit_vote:' || p_answer_id::TEXT);
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    BEGIN
        INSERT INTO votes (answer_id, voter_id, verdict)
        VALUES (p_answer_id, v_player_id, p_verdict);
    EXCEPTION
        WHEN unique_violation THEN
            RETURN _fail('You already voted on that.');
        WHEN check_violation THEN
            RETURN _fail('You can''t vote on your own answer.');
    END;
    PERFORM _catch_up(v_room_id, FALSE);
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION sync_room(p_token TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    PERFORM _catch_up(v_room_id, FALSE);
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION skip_phase(p_token TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_status TEXT;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT status INTO v_status FROM rooms WHERE id = v_room_id;
    IF v_status NOT IN ('prompt', 'voting') THEN
        RETURN _fail('Nothing to skip.');
    END IF;
    v_throttled := _throttle(v_player_id, 'skip_phase');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    PERFORM _catch_up(v_room_id, TRUE);
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION next_round(p_token TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_room rooms%ROWTYPE;
    v_prompt prompts%ROWTYPE;
    v_throttled JSONB;
    v_next INTEGER;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT * INTO v_room FROM rooms WHERE id = v_room_id FOR UPDATE;
    IF v_room.status = 'final_results' OR v_room.status <> 'leaderboard' THEN
        RETURN _build_view(v_player_id);
    END IF;
    v_throttled := _throttle(v_player_id, 'next_round');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    IF v_room.current_round >= v_room.total_rounds THEN
        UPDATE rooms SET status = 'final_results', phase_deadline = NULL WHERE id = v_room_id;
        RETURN _build_view(v_player_id);
    END IF;
    v_next := v_room.current_round + 1;
    SELECT * INTO v_prompt FROM prompts WHERE id = v_room.deck[v_next];
    INSERT INTO rounds (room_id, round_number, prompt_id, question_body, category)
    VALUES (v_room_id, v_next, v_prompt.id, v_prompt.body, v_prompt.category);
    UPDATE rooms
    SET current_round = v_next,
        status = 'prompt',
        phase_deadline = clock_timestamp() + make_interval(secs => v_room.answer_seconds)
    WHERE id = v_room_id;
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION play_again(p_token TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_status TEXT;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT status INTO v_status FROM rooms WHERE id = v_room_id FOR UPDATE;
    IF v_status = 'lobby' THEN
        RETURN _build_view(v_player_id);
    END IF;
    IF v_status <> 'final_results' THEN
        RETURN _fail('Finish the game before playing again.');
    END IF;
    v_throttled := _throttle(v_player_id, 'play_again');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    DELETE FROM rounds WHERE room_id = v_room_id;
    UPDATE rooms
    SET status = 'lobby',
        current_round = 0,
        deck = NULL,
        phase_deadline = NULL
    WHERE id = v_room_id;
    RETURN _build_view(v_player_id);
END;
$$;

CREATE OR REPLACE FUNCTION end_game(p_token TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_err JSONB;
    v_player_id UUID;
    v_room_id UUID;
    v_is_host BOOLEAN;
    v_status TEXT;
    v_throttled JSONB;
BEGIN
    SELECT err, player_id, room_id, is_host
    INTO v_err, v_player_id, v_room_id, v_is_host
    FROM _lock_player(p_token);
    IF v_err IS NOT NULL THEN
        RETURN v_err;
    END IF;
    IF NOT v_is_host THEN
        RETURN _fail('Only the host can do that.');
    END IF;
    SELECT status INTO v_status FROM rooms WHERE id = v_room_id FOR UPDATE;
    IF v_status = 'lobby' THEN
        RETURN _fail('The game hasn''t started.');
    END IF;
    IF v_status = 'final_results' THEN
        RETURN _build_view(v_player_id);
    END IF;
    v_throttled := _throttle(v_player_id, 'end_game');
    IF v_throttled IS NOT NULL THEN
        RETURN v_throttled;
    END IF;
    IF v_status IN ('prompt', 'voting') THEN
        PERFORM _catch_up(v_room_id, TRUE);
        SELECT status INTO v_status FROM rooms WHERE id = v_room_id;
        IF v_status = 'voting' THEN
            PERFORM _catch_up(v_room_id, TRUE);
        END IF;
    END IF;
    UPDATE rooms SET status = 'final_results', phase_deadline = NULL WHERE id = v_room_id;
    RETURN _build_view(v_player_id);
END;
$$;

-- ---------------------------------------------------------------------------
-- Privileges. Service role bypasses RLS. Everyone else is locked out.
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    fn TEXT;
    role_name TEXT;
BEGIN
    FOR fn IN
        SELECT p.oid::regprocedure::TEXT
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname IN (
            '_fail', '_iso', '_hash_token', '_clean_name', '_consensus', '_reject_self_vote',
            '_throttle', '_lock_player', '_finalize_round', '_maybe_advance', '_catch_up',
            '_leaderboard_standings', '_build_view',
            'create_room', 'join_room', 'reconnect', 'leave_room', 'update_settings',
            'save_custom_prompt', 'delete_custom_prompt', 'set_prompt_included', 'import_prompts',
            'start_game', 'submit_answer', 'submit_vote', 'sync_room', 'skip_phase',
            'next_round', 'play_again', 'end_game'
          )
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', fn);
        FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I', fn, role_name);
            END IF;
        END LOOP;
    END LOOP;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        FOREACH fn IN ARRAY ARRAY[
            'create_room(text)',
            'join_room(text, text)',
            'reconnect(text)',
            'leave_room(text)',
            'update_settings(text, integer, integer, integer, text[], text)',
            'save_custom_prompt(text, text, uuid)',
            'delete_custom_prompt(text, uuid)',
            'set_prompt_included(text, uuid, boolean)',
            'import_prompts(text, text)',
            'start_game(text)',
            'submit_answer(text, text)',
            'submit_vote(text, uuid, text)',
            'sync_room(text)',
            'skip_phase(text)',
            'next_round(text)',
            'play_again(text)',
            'end_game(text)'
        ] LOOP
            EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', fn);
        END LOOP;
    END IF;

    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'PUBLIC'] LOOP
        IF role_name = 'PUBLIC' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            IF role_name = 'PUBLIC' THEN
                EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC';
            ELSE
                EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', role_name);
            END IF;
        END IF;
    END LOOP;
END $$;
