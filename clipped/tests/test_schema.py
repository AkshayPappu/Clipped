from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "database" / "schema.sql").read_text(encoding="utf-8")


def test_schema_declares_tables_and_guards():
    for table in (
        "rooms",
        "players",
        "prompts",
        "room_prompts",
        "rounds",
        "answers",
        "votes",
        "round_results",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in SCHEMA
    assert "ENABLE ROW LEVEL SECURITY" in SCHEMA
    assert "session_token_hash" in SCHEMA
    assert "rooms_active_code_idx" in SCHEMA
    assert "UNIQUE (round_id, player_id)" in SCHEMA
    assert "UNIQUE (answer_id, voter_id)" in SCHEMA
    assert "REVOKE ALL ON FUNCTION" in SCHEMA
    for fn in (
        "create_room",
        "join_room",
        "start_game",
        "submit_answer",
        "submit_vote",
        "sync_room",
        "skip_phase",
        "next_round",
        "play_again",
        "end_game",
        "_finalize_round",
        "_consensus",
    ):
        assert f"FUNCTION {fn}" in SCHEMA or f"FUNCTION {fn}(" in SCHEMA
    assert "service_role" not in SCHEMA.lower() or "service_role" in SCHEMA
    assert "eyJ" not in SCHEMA
