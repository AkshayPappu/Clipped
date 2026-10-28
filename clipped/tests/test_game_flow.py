import json
import threading
from datetime import datetime, timedelta, timezone

from services.memory_store import MemoryStore
from utils.constants import (
    ERR_HOST,
    ERR_LOCKED,
    ERR_NAME,
    ERR_NEED_PLAYERS,
    ERR_SELF,
    ERR_SESSION,
    ERR_SLOW,
    ERR_STARTED,
    ERR_VOTED,
    MAX_PLAYERS,
)


def open_room(store: MemoryStore, names: list[str], start: bool = False, **settings):
    host = store.create_room(names[0])
    assert host["ok"], host
    tokens = [host["token"]]
    code = host["room"]["code"]
    for name in names[1:]:
        joined = store.join_room(code, name)
        assert joined["ok"], joined
        tokens.append(joined["token"])
    if settings:
        saved = store.update_settings(tokens[0], **settings)
        assert saved["ok"], saved
    if start:
        started = store.start_game(tokens[0])
        assert started["ok"], started
    return tokens, code


def test_room_code_collision_retries(store: MemoryStore):
    codes = iter(["1111", "1111", "2222"])
    store.code_source = lambda: next(codes)
    first = store.create_room("Ann")
    second = store.create_room("Bea")
    assert first["room"]["code"] == "1111"
    assert second["room"]["code"] == "2222"
    assert first["room"]["code"] != second["room"]["code"]


def test_duplicate_names_are_case_insensitive(store: MemoryStore):
    host = store.create_room("Mattie")
    taken = store.join_room(host["room"]["code"], "mattie")
    assert taken["error"] == ERR_NAME


def test_cannot_join_expired_room(store: MemoryStore):
    host = store.create_room("Ann")
    store.rooms[host["room"]["id"]].expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    joined = store.join_room(host["room"]["code"], "Bea")
    assert not joined["ok"]
    assert "expired" in joined["error"].lower()


def test_cannot_join_after_start(store: MemoryStore):
    _tokens, code = open_room(store, ["Ann", "Bea"], start=True)
    late = store.join_room(code, "Cy")
    assert late["error"] == ERR_STARTED


def test_room_caps_at_twelve(store: MemoryStore):
    host = store.create_room("P0")
    code = host["room"]["code"]
    for index in range(1, MAX_PLAYERS):
        assert store.join_room(code, f"P{index}")["ok"]
    overflow = store.join_room(code, "Extra")
    assert not overflow["ok"]


def test_start_requires_two_players_and_host(store: MemoryStore):
    host = store.create_room("Ann")
    solo = store.start_game(host["token"])
    assert solo["error"] == ERR_NEED_PLAYERS
    tokens, _code = open_room(store, ["Ann", "Bea"])
    denied = store.start_game(tokens[1])
    assert denied["error"] == ERR_HOST
    started = store.start_game(tokens[0])
    assert started["room"]["status"] == "prompt"
    assert started["prompt"]["question"]


def test_non_host_cannot_skip_or_advance(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True)
    assert store.skip_phase(tokens[1])["error"] == ERR_HOST
    assert store.next_round(tokens[1])["error"] == ERR_HOST
    assert store.end_game(tokens[1])["error"] == ERR_HOST
    assert store.play_again(tokens[1])["error"] == ERR_HOST
    assert store.update_settings(
        tokens[1], 5, 30, 30, ["lore"], "random"
    )["error"] == ERR_HOST


def test_prompt_hides_other_answers(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True)
    store.submit_answer(tokens[0], "BETA_SECRET_ANSWER")
    guest = store.sync_room(tokens[1])
    assert guest["room"]["status"] == "prompt"
    assert "BETA_SECRET_ANSWER" not in json.dumps(guest)
    assert guest["prompt"]["your_answer"] is None
    assert guest["prompt"]["submitted_count"] == 1
    assert guest["voting"] is None


def test_duplicate_answer_is_idempotent_then_rejected(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True)
    first = store.submit_answer(tokens[0], "same line")
    second = store.submit_answer(tokens[0], "same line")
    third = store.submit_answer(tokens[0], "different line")
    assert first["ok"] and second["ok"]
    assert third["error"] == ERR_LOCKED
    guest = store.sync_room(tokens[1])
    assert guest["prompt"]["submitted_count"] == 1


def test_self_vote_and_duplicate_vote(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True)
    store.submit_answer(tokens[0], "alpha answer")
    view = store.submit_answer(tokens[1], "beta answer")
    assert view["room"]["status"] == "voting"
    own = next(answer for answer in view["voting"]["answers"] if answer["is_own"])
    other = next(answer for answer in view["voting"]["answers"] if not answer["is_own"])
    assert "author" not in own and "player_id" not in own
    assert store.submit_vote(tokens[1], own["id"], "gem")["error"] == ERR_SELF
    assert store.submit_vote(tokens[1], other["id"], "gem")["ok"]
    assert store.submit_vote(tokens[1], other["id"], "gem")["ok"]
    changed = store.submit_vote(tokens[1], other["id"], "fake")
    assert changed["error"] == ERR_VOTED


def test_tie_breaks_to_lower_score(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea", "Cy"], start=True)
    store.submit_answer(tokens[0], "the parking lot incident")
    voting = store.skip_phase(tokens[0])
    answer_id = voting["voting"]["answers"][0]["id"]
    store.submit_vote(tokens[1], answer_id, "gem")
    board = store.submit_vote(tokens[2], answer_id, "common")
    reveal = board["leaderboard"]["reveals"][0]
    assert reveal["verdict"] == "common"
    assert reveal["points"] == 100
    assert reveal["author"] == "Ann"
    assert board["leaderboard"]["standings"][0]["display_name"] == "Ann"


def test_gem_fake_tie_is_fake(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea", "Cy"], start=True)
    store.submit_answer(tokens[0], "a suspicious story")
    voting = store.skip_phase(tokens[0])
    answer_id = voting["voting"]["answers"][0]["id"]
    store.submit_vote(tokens[1], answer_id, "gem")
    board = store.submit_vote(tokens[2], answer_id, "fake")
    reveal = board["leaderboard"]["reveals"][0]
    assert reveal["verdict"] == "fake"
    assert reveal["points"] == 0


def test_clear_gem_scores_300(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea", "Cy"], start=True)
    store.submit_answer(tokens[0], "legendary parking lot")
    voting = store.skip_phase(tokens[0])
    answer_id = voting["voting"]["answers"][0]["id"]
    store.submit_vote(tokens[1], answer_id, "gem")
    board = store.submit_vote(tokens[2], answer_id, "gem")
    reveal = board["leaderboard"]["reveals"][0]
    assert reveal == {
        **reveal,
        "verdict": "gem",
        "points": 300,
        "gem": 2,
        "common": 0,
        "fake": 0,
    }
    no_answer = next(row for row in board["leaderboard"]["standings"] if row["display_name"] == "Bea")
    assert no_answer["points"] == 0


def test_zero_vote_answers_score_nothing(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True)
    store.submit_answer(tokens[0], "alpha answer")
    store.submit_answer(tokens[1], "beta answer")
    board = store.skip_phase(tokens[0])
    assert board["room"]["status"] == "leaderboard"
    assert board["leaderboard"]["reveals"]
    assert all(item["points"] == 0 and item["verdict"] == "none" for item in board["leaderboard"]["reveals"])


def test_no_submission_scores_zero(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True)
    board = store.skip_phase(tokens[0])
    assert board["room"]["status"] == "leaderboard"
    assert board["leaderboard"]["reveals"] == []
    assert all(row["points"] == 0 for row in board["leaderboard"]["standings"])


def test_timer_advances_without_the_host(store: MemoryStore):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.clock = lambda: start
    tokens, _code = open_room(
        store,
        ["Ann", "Bea"],
        start=True,
        total_rounds=5,
        answer_seconds=30,
        vote_seconds=30,
        categories=["lore"],
        question_order="sequential",
    )
    store.submit_answer(tokens[0], "only the host answered")
    hidden = store.sync_room(tokens[1])
    assert "only the host answered" not in json.dumps(hidden["prompt"])
    store.clock = lambda: start + timedelta(seconds=31)
    view = store.sync_room(tokens[1])
    assert view["room"]["status"] == "voting"
    assert any(answer["body"] == "only the host answered" for answer in view["voting"]["answers"])


def test_double_phase_advance_is_idempotent(store: MemoryStore):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.clock = lambda: start
    tokens, _code = open_room(
        store,
        ["Ann", "Bea"],
        start=True,
        total_rounds=5,
        answer_seconds=30,
        vote_seconds=45,
        categories=["lore"],
        question_order="random",
    )
    room_id = store.sync_room(tokens[0])["room"]["id"]
    store.submit_answer(tokens[0], "solo answer text")
    store.clock = lambda: start + timedelta(seconds=31)
    results: list[dict] = []

    def work(token: str) -> None:
        results.append(store.sync_room(token))

    threads = [threading.Thread(target=work, args=(token,)) for token in tokens]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 2
    assert all(result["ok"] and result["room"]["status"] == "voting" for result in results)
    assert all(result["room"]["current_round"] == 1 for result in results)
    assert sum(1 for rnd in store.rounds.values() if rnd.room_id == room_id) == 1


def test_concurrent_answers_from_different_players(store: MemoryStore):
    tokens, _code = open_room(store, [f"P{i}" for i in range(5)], start=True)
    errors: list[dict] = []

    def work(index: int) -> None:
        result = store.submit_answer(tokens[index], f"unique-answer-{index}")
        if not result["ok"]:
            errors.append(result)

    threads = [threading.Thread(target=work, args=(index,)) for index in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    view = store.sync_room(tokens[0])
    assert view["room"]["status"] == "voting"
    assert len(view["voting"]["answers"]) == 5


def test_concurrent_duplicate_answer_from_same_player(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True)
    results: list[dict] = []

    def work(text: str) -> None:
        results.append(store.submit_answer(tokens[0], text))

    threads = [
        threading.Thread(target=work, args=("alpha-unique",)),
        threading.Thread(target=work, args=("beta-unique",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(result["ok"] for result in results) == 1
    assert sum(result.get("error") == ERR_LOCKED for result in results) == 1
    guest = store.sync_room(tokens[1])
    assert guest["prompt"]["submitted_count"] == 1


def test_reconnect_does_not_duplicate_player(store: MemoryStore):
    host = store.create_room("Ann")
    token = host["token"]
    player_id = host["you"]["id"]
    again = store.reconnect(token)
    assert again["ok"]
    assert again["you"]["id"] == player_id
    assert again["room"]["player_count"] == 1
    store.join_room(host["room"]["code"], "Bea")
    refreshed = store.reconnect(token)
    assert refreshed["room"]["player_count"] == 2
    assert sum(player.display_name == "Ann" for player in store.players.values()) == 1


def test_bad_token_rejected(store: MemoryStore):
    missing = store.sync_room("not-a-real-session-token")
    assert missing["error"] == ERR_SESSION


def test_rate_limit_on_repeated_settings(store: MemoryStore):
    store.mutation_gap = timedelta(milliseconds=300)
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.clock = lambda: moment
    host = store.create_room("Ann")
    token = host["token"]
    kwargs = dict(total_rounds=5, answer_seconds=30, vote_seconds=30, categories=["lore"], question_order="random")
    assert store.update_settings(token, **kwargs)["ok"]
    store.clock = lambda: moment + timedelta(milliseconds=100)
    limited = store.update_settings(token, **kwargs)
    assert limited["error"] == ERR_SLOW
    store.clock = lambda: moment + timedelta(milliseconds=400)
    assert store.update_settings(token, **kwargs)["ok"]


def test_next_round_cannot_skip_ahead(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True, total_rounds=5, answer_seconds=30, vote_seconds=30, categories=["lore"], question_order="sequential")
    store.skip_phase(tokens[0])
    first = store.next_round(tokens[0])
    assert first["room"]["status"] == "prompt"
    assert first["room"]["current_round"] == 2
    second = store.next_round(tokens[0])
    assert second["room"]["current_round"] == 2
    assert second["room"]["status"] == "prompt"


def test_play_again_keeps_players(store: MemoryStore):
    tokens, _code = open_room(store, ["Ann", "Bea"], start=True)
    store.end_game(tokens[0])
    again = store.play_again(tokens[0])
    assert again["room"]["status"] == "lobby"
    assert again["room"]["player_count"] == 2
    assert again["room"]["current_round"] == 0
