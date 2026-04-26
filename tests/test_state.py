import json

from sa_rebuild import state as state_mod


def test_save_and_resume_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "LAST_RUN_POINTER", tmp_path / "last_run.json")

    rs = state_mod.RunState.new(
        input_csv="input/x.csv",
        output_csv="output/x.csv",
        row_ids=[0, 1, 2],
    )
    state_mod.save(rs)
    assert rs.path().exists()
    assert (tmp_path / "last_run.json").exists()

    state_mod.mark_done(rs, 0, tokens_left=53)
    state_mod.mark_done(rs, 1, tokens_left=46)
    state_mod.mark_error(rs, 2, "U", "fetch", "boom")

    reloaded = state_mod.load_last()
    assert reloaded.rows_done == 2
    assert reloaded.completed_row_ids == [0, 1]
    assert reloaded.remaining_row_ids == [2]
    assert reloaded.tokens_left_snapshot == 46
    assert reloaded.errors[0]["row_id"] == 2


def test_atomic_write_no_tmp_left_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "LAST_RUN_POINTER", tmp_path / "last_run.json")
    rs = state_mod.RunState.new("i.csv", "o.csv", [0])
    state_mod.save(rs)
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    with rs.path().open() as f:
        json.load(f)


def test_duplicate_upc_rows_tracked_independently(tmp_path, monkeypatch):
    """Two rows with the same UPC but different costs should both run."""
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "LAST_RUN_POINTER", tmp_path / "last_run.json")
    rs = state_mod.RunState.new("i.csv", "o.csv", row_ids=[0, 1])  # same UPC at idx 0 and 1
    state_mod.save(rs)
    state_mod.mark_done(rs, 0, tokens_left=10)
    state_mod.mark_done(rs, 1, tokens_left=4)
    reloaded = state_mod.load_last()
    assert reloaded.rows_done == 2
    assert reloaded.completed_row_ids == [0, 1]


def test_completed_rows_are_not_double_processed(tmp_path, monkeypatch):
    """Resume must not re-process row_ids already in completed_row_ids,
    even if they're somehow still listed in remaining_row_ids."""
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "LAST_RUN_POINTER", tmp_path / "last_run.json")
    rs = state_mod.RunState.new("i.csv", "o.csv", row_ids=[0, 1, 2])
    state_mod.mark_done(rs, 0, tokens_left=50)
    state_mod.mark_done(rs, 1, tokens_left=44)
    # Simulate the corrupt-state case: row 1 in BOTH lists.
    rs.remaining_row_ids = [1, 2]
    state_mod.save(rs)
    reloaded = state_mod.load_last()
    # mark_done is idempotent — calling it twice for the same row_id is a no-op.
    state_mod.mark_done(reloaded, 1, tokens_left=40)
    assert reloaded.completed_row_ids.count(1) == 1
