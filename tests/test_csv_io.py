"""CSV input parsing + ReportWriter description-row behavior."""
from pathlib import Path

from sa_rebuild.fba.csv_io import COLUMN_DESCRIPTIONS, REPORT_COLUMNS, ReportWriter, read_input


def test_read_input_accepts_upc(tmp_path: Path):
    p = tmp_path / "in.csv"
    p.write_text("upc,cost\n123,9.99\n")
    rows = read_input(p)
    assert len(rows) == 1
    assert rows[0].upc == "123"
    assert rows[0].asin is None
    assert rows[0].lookup_key == "123"
    assert rows[0].lookup_is_asin is False


def test_read_input_accepts_asin(tmp_path: Path):
    p = tmp_path / "in.csv"
    p.write_text("asin,cost\nB001RCSARA,29.99\n")
    rows = read_input(p)
    assert rows[0].asin == "B001RCSARA"
    assert rows[0].upc is None
    assert rows[0].lookup_key == "B001RCSARA"
    assert rows[0].lookup_is_asin is True


def test_read_input_asin_wins_when_both_present(tmp_path: Path):
    p = tmp_path / "in.csv"
    p.write_text("upc,asin,cost\n123,B001RCSARA,9.99\n")
    rows = read_input(p)
    assert rows[0].lookup_key == "B001RCSARA"
    assert rows[0].lookup_is_asin is True


def test_read_input_assigns_distinct_row_ids(tmp_path: Path):
    """Same UPC twice with different costs both get processed (row_id distinct)."""
    p = tmp_path / "in.csv"
    p.write_text("upc,cost\n123,9.99\n123,8.50\n")
    rows = read_input(p)
    assert [r.row_id for r in rows] == [0, 1]
    assert [r.cost for r in rows] == [9.99, 8.50]


def test_report_writer_emits_description_row_after_header(tmp_path: Path):
    out = tmp_path / "r.csv"
    with ReportWriter(out, include_descriptions=True) as w:
        w.write({"upc": "123", "asin": "B0X", "cost": 1.0})
    lines = out.read_text().splitlines()
    assert lines[0] == ",".join(REPORT_COLUMNS)
    # The description row's `upc` cell tags itself for easy filtering/skipping.
    assert lines[1].startswith("[COLUMN HELP")
    # The description row contains the asin column's description text.
    assert COLUMN_DESCRIPTIONS["asin"] in lines[1]
    # The actual data row is third.
    assert lines[2].startswith("123,B0X,")


def test_report_writer_skips_descriptions_when_disabled(tmp_path: Path):
    out = tmp_path / "r.csv"
    with ReportWriter(out, include_descriptions=False) as w:
        w.write({"upc": "123", "cost": 1.0})
    lines = out.read_text().splitlines()
    assert lines[0] == ",".join(REPORT_COLUMNS)
    assert lines[1].startswith("123,")
