"""In-process game store.

Mirrors the Supabase RPCs: one lock stands in for row locks, unique keys stand
in for constraints, and scoring comes from scoring_service. All sessions on
one Streamlit process share a single instance. Production uses Supabase.
"""

from __future__ import annotations

import random
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from services.question_bank import load_builtin_prompts
from services.scoring_service import score_ballots
from utils.constants import (
    AWAY_SECONDS,
    CATEGORY_ORDER,
    ERR_ANSWER,
    ERR_CATEGORY,
    ERR_CODE,
    ERR_CODE_SPACE,
    ERR_DISPLAY,
    ERR_EXPIRED,
    ERR_FINISH,
    ERR_FULL,
    ERR_HOST,
    ERR_LOCKED,
    ERR_LONG_ANSWER,
    ERR_MIDGAME,
    ERR_MISSING,
    ERR_NAME,
    ERR_NEED_PLAYERS,
    ERR_NEED_QUESTIONS,
    ERR_NOT_STARTED,
    ERR_PROMPT,
    ERR_SESSION,
    ERR_SETTINGS,
    ERR_SKIP,
    ERR_SLOW,
    ERR_STARTED,
    ERR_TIME,
    ERR_VOTE,
    MAX_IMPORT,
    MAX_PLAYERS,
    MUTATION_GAP_MS,
    ORDER_OPTIONS,
    PHASE_FINAL,
    PHASE_LEADERBOARD,
    PHASE_LOBBY,
    PHASE_PROMPT,
    PHASE_VOTING,
    ROOM_TTL_HOURS,
    ROUND_OPTIONS,
    TIMER_OPTIONS,
    clean_answer,
    clean_categories,
    clean_code,
    clean_name,
    clean_prompt,
    fail,
)


def _hash(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Prompt:
    id: str
    category: str
    body: str
    builtin: bool
    sort_index: int
    room_id: str | None = None
    included: bool = True
    created_at: datetime = field(default_factory=_now_utc)


@dataclass
class Player:
    id: str
    room_id: str
    display_name: str
    token_hash: str
    is_host: bool
    joined_at: datetime
    last_seen: datetime
    left_at: datetime | None = None
    last_actions: dict[str, datetime] = field(default_factory=dict)


@dataclass
class Room:
    id: str
    code: str
    status: str
    host_player_id: str | None
    total_rounds: int
    answer_seconds: int
    vote_seconds: int
    categories: list[str]
    question_order: str
    phase_deadline: datetime | None
    current_round: int
    created_at: datetime
    expires_at: datetime
    deck: list[str] = field(default_factory=list)


@dataclass
class Round:
    id: str
    room_id: str
    number: int
    prompt_id: str
    question: str
    category: str
    finalized: bool = False


@dataclass
class Answer:
    id: str
    round_id: str
    player_id: str
    body: str
    submitted_at: datetime
    display_order: int = 0


@dataclass
class Result:
    round_id: str
    answer_id: str
    player_id: str
    place: int
    points: int
    borda: int
    tied: bool


class MemoryStore:
    local_mode = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.mutation_gap = timedelta(milliseconds=MUTATION_GAP_MS)
        self.clock: Callable[[], datetime] | None = None
        self.code_source: Callable[[], str] | None = None
        self.rng: random.Random | None = None
        self.rooms: dict[str, Room] = {}
        self.players: dict[str, Player] = {}
        self.hash_to_player: dict[str, str] = {}
        self.rounds: dict[str, Round] = {}
        self.answers: dict[str, Answer] = {}
        self.rankings: dict[str, list[str]] = {}
        self.results: dict[str, Result] = {}
        self.prompts: dict[str, Prompt] = {}
        self.builtin_ids: list[str] = []
        for prompt_id, category, body, sort_index in load_builtin_prompts():
            self.prompts[prompt_id] = Prompt(
                id=prompt_id,
                category=category,
                body=body,
                builtin=True,
                sort_index=sort_index,
            )
            self.builtin_ids.append(prompt_id)

    def create_room(self, display_name: str) -> dict:
        with self._lock:
            return self._create_room(display_name)

    def join_room(self, code: str, display_name: str) -> dict:
        with self._lock:
            return self._join_room(code, display_name)

    def reconnect(self, token: str) -> dict:
        with self._lock:
            player, room, error = self._auth(token)
            if error:
                return error
            assert player and room
            return self._view(player, room)

    def leave_room(self, token: str) -> dict:
        with self._lock:
            return self._leave_room(token)

    def update_settings(
        self,
        token: str,
        total_rounds: int,
        answer_seconds: int,
        vote_seconds: int,
        categories: list[str],
        question_order: str,
    ) -> dict:
        with self._lock:
            return self._update_settings(
                token, total_rounds, answer_seconds, vote_seconds, categories, question_order
            )

    def save_custom_prompt(self, token: str, body: str, prompt_id: str | None = None) -> dict:
        with self._lock:
            return self._save_custom_prompt(token, body, prompt_id)

    def delete_custom_prompt(self, token: str, prompt_id: str) -> dict:
        with self._lock:
            return self._delete_custom_prompt(token, prompt_id)

    def set_prompt_included(self, token: str, prompt_id: str, included: bool) -> dict:
        with self._lock:
            return self._set_prompt_included(token, prompt_id, included)

    def import_prompts(self, token: str, raw_text: str) -> dict:
        with self._lock:
            return self._import_prompts(token, raw_text)

    def start_game(self, token: str) -> dict:
        with self._lock:
            return self._start_game(token)

    def submit_answer(self, token: str, body: str) -> dict:
        with self._lock:
            return self._submit_answer(token, body)

    def submit_ranking(self, token: str, answer_ids: list[str]) -> dict:
        with self._lock:
            return self._submit_ranking(token, answer_ids)

    def sync_room(self, token: str) -> dict:
        with self._lock:
            player, room, error = self._auth(token)
            if error:
                return error
            assert player and room
            self._catch_up(room, self._now(), force=False)
            return self._view(player, room)

    def skip_phase(self, token: str) -> dict:
        with self._lock:
            return self._skip_phase(token)

    def next_round(self, token: str) -> dict:
        with self._lock:
            return self._next_round(token)

    def play_again(self, token: str) -> dict:
        with self._lock:
            return self._play_again(token)

    def end_game(self, token: str) -> dict:
        with self._lock:
            return self._end_game(token)

    def _now(self) -> datetime:
        if self.clock is not None:
            return self.clock()
        return _now_utc()

    def _create_room(self, display_name: str) -> dict:
        name = clean_name(display_name)
        if not name:
            return fail(ERR_DISPLAY)
        code = self._mint_code()
        if not code:
            return fail(ERR_CODE_SPACE)
        now = self._now()
        room = Room(
            id=_id(),
            code=code,
            status=PHASE_LOBBY,
            host_player_id=None,
            total_rounds=5,
            answer_seconds=60,
            vote_seconds=45,
            categories=list(CATEGORY_ORDER),
            question_order="random",
            phase_deadline=None,
            current_round=0,
            created_at=now,
            expires_at=now + timedelta(hours=ROOM_TTL_HOURS),
        )
        token = secrets.token_hex(32)
        player = Player(
            id=_id(),
            room_id=room.id,
            display_name=name,
            token_hash=_hash(token),
            is_host=True,
            joined_at=now,
            last_seen=now,
        )
        room.host_player_id = player.id
        self.rooms[room.id] = room
        self.players[player.id] = player
        self.hash_to_player[player.token_hash] = player.id
        return self._view(player, room, token=token)

    def _join_room(self, code: str, display_name: str) -> dict:
        name = clean_name(display_name)
        if not name:
            return fail(ERR_DISPLAY)
        cleaned = clean_code(code)
        if not cleaned:
            return fail(ERR_CODE)
        room = self._active_room_by_code(cleaned)
        if room is None:
            if any(item.code == cleaned for item in self.rooms.values()):
                return fail(ERR_EXPIRED)
            return fail(ERR_MISSING)
        now = self._now()
        if room.expires_at <= now or room.status == "expired":
            room.status = "expired"
            return fail(ERR_EXPIRED)
        if room.status != PHASE_LOBBY:
            return fail(ERR_STARTED)
        active = self._active_players(room.id)
        if len(active) >= MAX_PLAYERS:
            return fail(ERR_FULL)
        if any(player.display_name.lower() == name.lower() for player in active):
            return fail(ERR_NAME)
        token = secrets.token_hex(32)
        player = Player(
            id=_id(),
            room_id=room.id,
            display_name=name,
            token_hash=_hash(token),
            is_host=False,
            joined_at=now,
            last_seen=now,
        )
        self.players[player.id] = player
        self.hash_to_player[player.token_hash] = player.id
        return self._view(player, room, token=token)

    def _leave_room(self, token: str) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        now = self._now()
        player.left_at = now
        player.is_host = False
        if room.host_player_id == player.id:
            remaining = self._active_players(room.id)
            if remaining:
                remaining.sort(key=lambda item: item.joined_at)
                nxt = remaining[0]
                nxt.is_host = True
                room.host_player_id = nxt.id
            else:
                room.status = "expired"
        self.hash_to_player.pop(player.token_hash, None)
        return {"ok": True}

    def _update_settings(
        self,
        token: str,
        total_rounds: int,
        answer_seconds: int,
        vote_seconds: int,
        categories: list[str],
        question_order: str,
    ) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        if not player.is_host:
            return fail(ERR_HOST)
        if room.status != PHASE_LOBBY:
            return fail(ERR_MIDGAME)
        cats = clean_categories(list(categories))
        if cats is None:
            return fail(ERR_CATEGORY)
        if total_rounds not in ROUND_OPTIONS or answer_seconds not in TIMER_OPTIONS or vote_seconds not in TIMER_OPTIONS:
            return fail(ERR_SETTINGS)
        if question_order not in ORDER_OPTIONS:
            return fail(ERR_SETTINGS)
        blocked = self._throttle(player, "update_settings")
        if blocked:
            return blocked
        room.total_rounds = int(total_rounds)
        room.answer_seconds = int(answer_seconds)
        room.vote_seconds = int(vote_seconds)
        room.categories = cats
        room.question_order = question_order
        return self._view(player, room)

    def _save_custom_prompt(self, token: str, body: str, prompt_id: str | None) -> dict:
        player, room, error = self._host_lobby(token)
        if error:
            return error
        assert player and room
        cleaned = clean_prompt(body)
        if not cleaned:
            return fail(ERR_PROMPT)
        blocked = self._throttle(player, "save_custom_prompt")
        if blocked:
            return blocked
        if prompt_id:
            prompt = self.prompts.get(prompt_id)
            if not prompt or prompt.builtin or prompt.room_id != room.id:
                return fail(ERR_PROMPT)
            prompt.body = cleaned
        else:
            now = self._now()
            prompt = Prompt(
                id=_id(),
                category="custom",
                body=cleaned,
                builtin=False,
                sort_index=self._next_sort(),
                room_id=room.id,
                included=True,
                created_at=now,
            )
            self.prompts[prompt.id] = prompt
        return self._view(player, room)

    def _delete_custom_prompt(self, token: str, prompt_id: str) -> dict:
        player, room, error = self._host_lobby(token)
        if error:
            return error
        assert player and room
        prompt = self.prompts.get(prompt_id)
        if not prompt or prompt.builtin or prompt.room_id != room.id:
            return fail(ERR_PROMPT)
        blocked = self._throttle(player, "delete_custom_prompt")
        if blocked:
            return blocked
        self.prompts.pop(prompt_id, None)
        return self._view(player, room)

    def _set_prompt_included(self, token: str, prompt_id: str, included: bool) -> dict:
        player, room, error = self._host_lobby(token)
        if error:
            return error
        assert player and room
        prompt = self.prompts.get(prompt_id)
        if not prompt or prompt.builtin or prompt.room_id != room.id:
            return fail(ERR_PROMPT)
        blocked = self._throttle(player, "set_prompt_included")
        if blocked:
            return blocked
        prompt.included = bool(included)
        return self._view(player, room)

    def _import_prompts(self, token: str, raw_text: str) -> dict:
        player, room, error = self._host_lobby(token)
        if error:
            return error
        assert player and room
        blocked = self._throttle(player, "import_prompts")
        if blocked:
            return blocked
        added = 0
        skipped = 0
        existing = {
            prompt.body.lower()
            for prompt in self.prompts.values()
            if prompt.room_id == room.id or prompt.builtin
        }
        for line in (raw_text or "").splitlines():
            if added >= MAX_IMPORT:
                skipped += 1
                continue
            cleaned = clean_prompt(line)
            if not cleaned or cleaned.lower() in existing:
                if line.strip():
                    skipped += 1
                continue
            now = self._now()
            prompt = Prompt(
                id=_id(),
                category="custom",
                body=cleaned,
                builtin=False,
                sort_index=self._next_sort(),
                room_id=room.id,
                included=True,
                created_at=now,
            )
            self.prompts[prompt.id] = prompt
            existing.add(cleaned.lower())
            added += 1
        view = self._view(player, room)
        view["added"] = added
        view["skipped"] = skipped
        return view

    def _start_game(self, token: str) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        if not player.is_host:
            return fail(ERR_HOST)
        if room.status != PHASE_LOBBY:
            return self._view(player, room)
        if len(self._active_players(room.id)) < 2:
            return fail(ERR_NEED_PLAYERS)
        pool = self._pool(room)
        if len(pool) < room.total_rounds:
            return fail(ERR_NEED_QUESTIONS)
        blocked = self._throttle(player, "start_game")
        if blocked:
            return blocked
        chosen = list(pool)
        if room.question_order == "sequential":
            chosen.sort(key=lambda item: (self._category_rank(item.category), item.sort_index, item.body))
        else:
            self._shuffler().shuffle(chosen)
        chosen = chosen[: room.total_rounds]
        room.deck = [item.id for item in chosen]
        room.current_round = 1
        now = self._now()
        self._open_round(room, chosen[0], now)
        return self._view(player, room)

    def _submit_answer(self, token: str, body: str) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        self._catch_up(room, self._now(), force=False)
        if room.status != PHASE_PROMPT:
            return fail(ERR_TIME)
        cleaned, answer_error = clean_answer(body)
        if answer_error or not cleaned:
            return fail(answer_error or ERR_ANSWER)
        rnd = self._current_round(room)
        if rnd is None:
            return fail(ERR_TIME)
        existing = self._answer_for(rnd.id, player.id)
        if existing:
            if existing.body == cleaned:
                return self._view(player, room)
            return fail(ERR_LOCKED)
        blocked = self._throttle(player, "submit_answer")
        if blocked:
            return blocked
        now = self._now()
        answer = Answer(
            id=_id(),
            round_id=rnd.id,
            player_id=player.id,
            body=cleaned,
            submitted_at=now,
        )
        self.answers[answer.id] = answer
        self._catch_up(room, now, force=False)
        return self._view(player, room)

    def _submit_ranking(self, token: str, answer_ids: list[str]) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        self._catch_up(room, self._now(), force=False)
        if room.status != PHASE_VOTING:
            return fail(ERR_TIME)
        rnd = self._current_round(room)
        if rnd is None:
            return fail(ERR_TIME)
        expected = [answer.id for answer in self._round_answers(rnd.id)]
        if not answer_ids or len(answer_ids) != len(set(answer_ids)) or set(answer_ids) != set(expected):
            return fail(ERR_VOTE)
        key = _ranking_key(rnd.id, player.id)
        existing = self.rankings.get(key)
        if existing is not None:
            if existing == list(answer_ids):
                return self._view(player, room)
            return fail(ERR_LOCKED)
        blocked = self._throttle(player, "submit_ranking")
        if blocked:
            return blocked
        self.rankings[key] = list(answer_ids)
        self._catch_up(room, self._now(), force=False)
        return self._view(player, room)

    def _skip_phase(self, token: str) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        if not player.is_host:
            return fail(ERR_HOST)
        if room.status not in (PHASE_PROMPT, PHASE_VOTING):
            return fail(ERR_SKIP)
        blocked = self._throttle(player, "skip_phase")
        if blocked:
            return blocked
        self._catch_up(room, self._now(), force=True)
        return self._view(player, room)

    def _next_round(self, token: str) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        if not player.is_host:
            return fail(ERR_HOST)
        if room.status == PHASE_FINAL:
            return self._view(player, room)
        if room.status != PHASE_LEADERBOARD:
            return self._view(player, room)
        blocked = self._throttle(player, "next_round")
        if blocked:
            return blocked
        now = self._now()
        if room.current_round >= room.total_rounds:
            room.status = PHASE_FINAL
            room.phase_deadline = None
            return self._view(player, room)
        room.current_round += 1
        prompt = self.prompts[room.deck[room.current_round - 1]]
        self._open_round(room, prompt, now)
        return self._view(player, room)

    def _play_again(self, token: str) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        if not player.is_host:
            return fail(ERR_HOST)
        if room.status == PHASE_LOBBY:
            return self._view(player, room)
        if room.status != PHASE_FINAL:
            return fail(ERR_FINISH)
        blocked = self._throttle(player, "play_again")
        if blocked:
            return blocked
        self._wipe_rounds(room.id)
        room.deck = []
        room.current_round = 0
        room.status = PHASE_LOBBY
        room.phase_deadline = None
        return self._view(player, room)

    def _end_game(self, token: str) -> dict:
        player, room, error = self._auth(token)
        if error:
            return error
        assert player and room
        if not player.is_host:
            return fail(ERR_HOST)
        if room.status == PHASE_LOBBY:
            return fail(ERR_NOT_STARTED)
        if room.status == PHASE_FINAL:
            return self._view(player, room)
        blocked = self._throttle(player, "end_game")
        if blocked:
            return blocked
        now = self._now()
        if room.status in (PHASE_PROMPT, PHASE_VOTING):
            self._catch_up(room, now, force=True)
            if room.status == PHASE_VOTING:
                self._catch_up(room, now, force=True)
        room.status = PHASE_FINAL
        room.phase_deadline = None
        return self._view(player, room)

    def _host_lobby(self, token: str) -> tuple[Player | None, Room | None, dict | None]:
        player, room, error = self._auth(token)
        if error:
            return None, None, error
        assert player and room
        if not player.is_host:
            return None, None, fail(ERR_HOST)
        if room.status != PHASE_LOBBY:
            return None, None, fail(ERR_MIDGAME)
        return player, room, None

    def _auth(self, token: str) -> tuple[Player | None, Room | None, dict | None]:
        if not token or len(token) < 16:
            return None, None, fail(ERR_SESSION)
        player_id = self.hash_to_player.get(_hash(token))
        if not player_id:
            return None, None, fail(ERR_SESSION)
        player = self.players[player_id]
        if player.left_at is not None:
            return None, None, fail(ERR_SESSION)
        room = self.rooms[player.room_id]
        now = self._now()
        if room.status == "expired" or room.expires_at <= now:
            room.status = "expired"
            return None, None, fail(ERR_EXPIRED)
        player.last_seen = now
        return player, room, None

    def _throttle(self, player: Player, action: str) -> dict | None:
        now = self._now()
        previous = player.last_actions.get(action)
        if self.mutation_gap > timedelta(0) and previous and now - previous < self.mutation_gap:
            return fail(ERR_SLOW)
        player.last_actions[action] = now
        return None

    def _mint_code(self) -> str | None:
        active = {room.code for room in self.rooms.values() if room.status != "expired"}
        for _ in range(50):
            if self.code_source is not None:
                code = self.code_source()
            else:
                code = f"{random.randint(0, 9999):04d}"
            if code not in active and clean_code(code):
                return code
        return None

    def _active_room_by_code(self, code: str) -> Room | None:
        matches = [room for room in self.rooms.values() if room.code == code and room.status != "expired"]
        if not matches:
            return None
        matches.sort(key=lambda room: room.created_at, reverse=True)
        return matches[0]

    def _active_players(self, room_id: str) -> list[Player]:
        people = [
            player
            for player in self.players.values()
            if player.room_id == room_id and player.left_at is None
        ]
        people.sort(key=lambda player: player.joined_at)
        return people

    def _pool(self, room: Room) -> list[Prompt]:
        selected = set(room.categories)
        pool = [
            self.prompts[prompt_id]
            for prompt_id in self.builtin_ids
            if self.prompts[prompt_id].category in selected
        ]
        customs = [
            prompt
            for prompt in self.prompts.values()
            if prompt.room_id == room.id and prompt.included and not prompt.builtin
        ]
        customs.sort(key=lambda prompt: prompt.created_at)
        return pool + customs

    def _category_rank(self, category: str) -> int:
        try:
            return CATEGORY_ORDER.index(category)
        except ValueError:
            return len(CATEGORY_ORDER)

    def _shuffler(self) -> random.Random:
        if self.rng is not None:
            return self.rng
        return random.SystemRandom()

    def _next_sort(self) -> int:
        if not self.prompts:
            return 1
        return max(prompt.sort_index for prompt in self.prompts.values()) + 1

    def _open_round(self, room: Room, prompt: Prompt, now: datetime) -> Round:
        rnd = Round(
            id=_id(),
            room_id=room.id,
            number=room.current_round,
            prompt_id=prompt.id,
            question=prompt.body,
            category=prompt.category,
        )
        self.rounds[rnd.id] = rnd
        room.status = PHASE_PROMPT
        room.phase_deadline = now + timedelta(seconds=room.answer_seconds)
        return rnd

    def _current_round(self, room: Room) -> Round | None:
        for rnd in self.rounds.values():
            if rnd.room_id == room.id and rnd.number == room.current_round:
                return rnd
        return None

    def _round_answers(self, round_id: str) -> list[Answer]:
        rows = [answer for answer in self.answers.values() if answer.round_id == round_id]
        rows.sort(key=lambda answer: (answer.display_order, answer.submitted_at))
        return rows

    def _answer_for(self, round_id: str, player_id: str) -> Answer | None:
        for answer in self.answers.values():
            if answer.round_id == round_id and answer.player_id == player_id:
                return answer
        return None

    def _catch_up(self, room: Room, now: datetime, force: bool) -> None:
        forced = force
        for _ in range(3):
            before = (room.status, room.current_round, room.phase_deadline)
            self._maybe_advance(room, now, force=forced)
            forced = False
            after = (room.status, room.current_round, room.phase_deadline)
            if after == before:
                break

    def _maybe_advance(self, room: Room, now: datetime, force: bool) -> None:
        if room.status == PHASE_PROMPT:
            rnd = self._current_round(room)
            if rnd is None:
                return
            answers = self._round_answers(rnd.id)
            active = self._active_players(room.id)
            deadline_hit = room.phase_deadline is not None and now >= room.phase_deadline
            if force or len(answers) >= len(active) or deadline_hit:
                if not answers:
                    rnd.finalized = True
                    room.status = PHASE_LEADERBOARD
                    room.phase_deadline = None
                else:
                    order = list(answers)
                    self._shuffler().shuffle(order)
                    for index, answer in enumerate(order):
                        answer.display_order = index
                    room.status = PHASE_VOTING
                    room.phase_deadline = now + timedelta(seconds=room.vote_seconds)
        elif room.status == PHASE_VOTING:
            rnd = self._current_round(room)
            if rnd is None:
                return
            deadline_hit = room.phase_deadline is not None and now >= room.phase_deadline
            if force or self._rankings_complete(room, rnd) or deadline_hit:
                self._finalize(rnd)
                room.status = PHASE_LEADERBOARD
                room.phase_deadline = None

    def _rankings_complete(self, room: Room, rnd: Round) -> bool:
        if not self._round_answers(rnd.id):
            return False
        active = self._active_players(room.id)
        return all(_ranking_key(rnd.id, voter.id) in self.rankings for voter in active)

    def _finalize(self, rnd: Round) -> None:
        if rnd.finalized:
            return
        answers = self._round_answers(rnd.id)
        ballots = [
            order
            for key, order in self.rankings.items()
            if key.startswith(f"{rnd.id}:")
        ]
        scored = {row["answer_id"]: row for row in score_ballots([answer.id for answer in answers], ballots)}
        for answer in answers:
            row = scored[answer.id]
            self.results[f"{rnd.id}:{answer.id}"] = Result(
                round_id=rnd.id,
                answer_id=answer.id,
                player_id=answer.player_id,
                place=row["place"],
                points=row["points"],
                borda=row["borda"],
                tied=row["tied"],
            )
        rnd.finalized = True

    def _wipe_rounds(self, room_id: str) -> None:
        round_ids = [rnd.id for rnd in self.rounds.values() if rnd.room_id == room_id]
        for round_id in round_ids:
            answer_ids = [answer.id for answer in self.answers.values() if answer.round_id == round_id]
            for answer_id in answer_ids:
                self.answers.pop(answer_id, None)
            for key in [key for key in self.rankings if key.startswith(f"{round_id}:")]:
                self.rankings.pop(key, None)
            for key in [key for key, result in self.results.items() if result.round_id == round_id]:
                self.results.pop(key, None)
            self.rounds.pop(round_id, None)

    def _room_results(self, room_id: str) -> list[Result]:
        return [
            result
            for result in self.results.values()
            if result.round_id in self.rounds and self.rounds[result.round_id].room_id == room_id
        ]

    def _standings(self, room: Room, exclude_round_id: str | None = None) -> list[dict]:
        players = self._active_players(room.id)
        points = {player.id: 0 for player in players}
        firsts = {player.id: 0 for player in players}
        round_points = {player.id: 0 for player in players}
        current = self._current_round(room)
        for result in self._room_results(room.id):
            if result.player_id not in points:
                continue
            if exclude_round_id and result.round_id == exclude_round_id:
                continue
            points[result.player_id] += result.points
            if result.place == 1 and not result.tied:
                firsts[result.player_id] += 1
            if current and result.round_id == current.id and exclude_round_id is None:
                round_points[result.player_id] += result.points
        ordered = sorted(players, key=lambda player: (-points[player.id], -firsts[player.id], player.display_name.lower()))
        return [
            {
                "rank": index + 1,
                "display_name": player.display_name,
                "points": points[player.id],
                "firsts": firsts[player.id],
                "round_points": round_points[player.id],
                "player_id": player.id,
            }
            for index, player in enumerate(ordered)
        ]

    def _view(self, player: Player, room: Room, token: str | None = None) -> dict:
        now = self._now()
        active = self._active_players(room.id)
        payload: dict = {
            "ok": True,
            "local_mode": True,
            "server_now": _iso(now),
            "room": {
                "id": room.id,
                "code": room.code,
                "status": room.status,
                "phase_deadline": _iso(room.phase_deadline),
                "current_round": room.current_round,
                "total_rounds": room.total_rounds,
                "answer_seconds": room.answer_seconds,
                "vote_seconds": room.vote_seconds,
                "categories": list(room.categories),
                "question_order": room.question_order,
                "player_count": len(active),
                "max_players": MAX_PLAYERS,
                "expires_at": _iso(room.expires_at),
            },
            "you": {
                "id": player.id,
                "display_name": player.display_name,
                "is_host": player.is_host,
            },
            "players": [
                {
                    "id": person.id,
                    "display_name": person.display_name,
                    "is_host": person.is_host,
                    "is_away": (now - person.last_seen).total_seconds() > AWAY_SECONDS,
                    "joined_at": _iso(person.joined_at),
                }
                for person in active
            ],
            "prompt": None,
            "voting": None,
            "leaderboard": None,
            "final": None,
            "custom_prompts": [],
            "deck_count": 0,
        }
        if token:
            payload["token"] = token
        if room.status == PHASE_LOBBY:
            payload["custom_prompts"] = [
                {"id": prompt.id, "body": prompt.body, "included": prompt.included}
                for prompt in sorted(
                    (
                        prompt
                        for prompt in self.prompts.values()
                        if prompt.room_id == room.id and not prompt.builtin
                    ),
                    key=lambda prompt: prompt.created_at,
                )
            ]
            payload["deck_count"] = len(self._pool(room))
        rnd = self._current_round(room)
        if room.status == PHASE_PROMPT and rnd:
            yours = self._answer_for(rnd.id, player.id)
            payload["prompt"] = {
                "round_number": rnd.number,
                "total_rounds": room.total_rounds,
                "question": rnd.question,
                "category": rnd.category,
                "submitted_count": len(self._round_answers(rnd.id)),
                "player_count": len(active),
                "your_answer": yours.body if yours else None,
                "deadline": _iso(room.phase_deadline),
            }
        elif room.status == PHASE_VOTING and rnd:
            answers = self._round_answers(rnd.id)
            needed, cast = self._ranking_progress(room, rnd)
            payload["voting"] = {
                "round_number": rnd.number,
                "total_rounds": room.total_rounds,
                "question": rnd.question,
                "category": rnd.category,
                "deadline": _iso(room.phase_deadline),
                "rankings_in": cast,
                "rankings_needed": needed,
                "your_order": self.rankings.get(_ranking_key(rnd.id, player.id)),
                "answers": [
                    {
                        "id": answer.id,
                        "body": answer.body,
                        "is_own": answer.player_id == player.id,
                    }
                    for answer in answers
                ],
            }
        elif room.status == PHASE_LEADERBOARD and rnd:
            payload["leaderboard"] = self._leaderboard_payload(room, rnd)
        elif room.status == PHASE_FINAL:
            payload["final"] = self._final_payload(room)
        return payload

    def _ranking_progress(self, room: Room, rnd: Round) -> tuple[int, int]:
        active = self._active_players(room.id)
        cast = sum(_ranking_key(rnd.id, voter.id) in self.rankings for voter in active)
        return len(active), cast

    def _leaderboard_payload(self, room: Room, rnd: Round) -> dict:
        current = self._standings(room)
        previous = self._standings(room, exclude_round_id=rnd.id)
        previous_rank = {row["player_id"]: row["rank"] for row in previous}
        standings = []
        for row in current:
            public = {key: value for key, value in row.items() if key != "player_id"}
            public["delta"] = previous_rank.get(row["player_id"], row["rank"]) - row["rank"]
            standings.append(public)
        answers = self._round_answers(rnd.id)
        spots = _spot_counts(rnd.id, [answer.id for answer in answers], self.rankings)
        reveals = []
        for answer in answers:
            result = self.results.get(f"{rnd.id}:{answer.id}")
            if result is None:
                continue
            author = self.players[answer.player_id].display_name
            reveals.append(
                {
                    "body": answer.body,
                    "author": author,
                    "place": result.place,
                    "points": result.points,
                    "tied": result.tied,
                    "spots": spots[answer.id],
                    "order": answer.display_order,
                }
            )
        reveals.sort(key=lambda item: (-item["points"], item["place"] or 10**9, item["order"]))
        for item in reveals:
            item.pop("order", None)
        return {
            "round_number": rnd.number,
            "total_rounds": room.total_rounds,
            "is_final_round": room.current_round >= room.total_rounds,
            "question": rnd.question,
            "category": rnd.category,
            "reveals": reveals,
            "standings": standings,
        }

    def _final_payload(self, room: Room) -> dict:
        standings = []
        for row in self._standings(room):
            public = {key: value for key, value in row.items() if key != "player_id"}
            public["delta"] = 0
            standings.append(public)
        top = standings[0]["points"] if standings else 0
        winners = [row["display_name"] for row in standings if row["points"] == top]
        results = self._room_results(room.id)
        best = None
        if results:
            def sort_key(result: Result) -> tuple:
                answer = self.answers[result.answer_id]
                return (-result.points, result.place or 10**9, answer.submitted_at, answer.body)

            chosen = min(results, key=sort_key)
            answer = self.answers[chosen.answer_id]
            best = {
                "body": answer.body,
                "author": self.players[answer.player_id].display_name,
                "points": chosen.points,
                "place": chosen.place,
            }
        return {
            "winners": winners,
            "tied": len(winners) > 1,
            "standings": standings,
            "best_answer": best,
            "firsts": sum(result.place == 1 and not result.tied for result in results),
            "total_answers": len(results),
        }


def _id() -> str:
    return str(__import__("uuid").uuid4())


def _ranking_key(round_id: str, voter_id: str) -> str:
    return f"{round_id}:{voter_id}"


def _spot_counts(round_id: str, answer_ids: list[str], rankings: dict[str, list[str]]) -> dict[str, list[int]]:
    """How many ballots put each answer in each spot. Index 0 is first place."""
    width = len(answer_ids)
    counts = {answer_id: [0] * width for answer_id in answer_ids}
    prefix = f"{round_id}:"
    for key, order in rankings.items():
        if not key.startswith(prefix):
            continue
        for index, answer_id in enumerate(order):
            row = counts.get(answer_id)
            if row is not None and index < width:
                row[index] += 1
    return counts
