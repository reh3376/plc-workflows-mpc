"""Tests that the customer-facing PLC-side templates ship and have expected structure."""

from __future__ import annotations

import csv
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "plc" / "templates"


def test_templates_directory_exists():
    assert _TEMPLATES_DIR.is_dir()


def test_st_routine_present_and_contains_permissive_logic():
    st_path = _TEMPLATES_DIR / "MPC_Supervisor.st"
    assert st_path.is_file()
    text = st_path.read_text(encoding="utf-8")
    assert "MPC_Permissive" in text
    assert "MPC_Service_Alive" in text
    assert "MPC_Rearm_OK" in text
    assert "Reactor_Temp_SP_Active" in text


def test_ladder_description_present():
    ladder = _TEMPLATES_DIR / "LADDER_DESCRIPTION.md"
    assert ladder.is_file()
    text = ladder.read_text(encoding="utf-8")
    assert "Rung 5 — Master permissive" in text
    assert "Periodic Task at 100 ms" in text


def test_readme_documents_apply_steps():
    readme = _TEMPLATES_DIR / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "How to apply" in text
    assert "Renaming for your loop" in text


def test_tags_csv_has_required_supervisor_tags():
    tags_path = _TEMPLATES_DIR / "TAGS.csv"
    assert tags_path.is_file()
    with tags_path.open() as fh:
        rows = list(csv.DictReader(fh))
    names = {row["tag_name"] for row in rows}
    required = {
        "MPC_Enable",
        "MPC_Active",
        "MPC_Heartbeat",
        "PLC_Heartbeat",
        "MPC_Service_Alive",
        "MPC_Rearm_OK",
        "MPC_Permissive",
        "MPC_Temp_SP",
        "MPC_SP_Min",
        "MPC_SP_Max",
        "Reactor_Temp_SP",
        "Reactor_Temp_SP_Local",
        "Reactor_Temp_SP_Active",
    }
    missing = required - names
    assert not missing, f"missing required supervisor tags: {sorted(missing)}"


def test_csv_header_matches_documented_columns():
    tags_path = _TEMPLATES_DIR / "TAGS.csv"
    with tags_path.open() as fh:
        reader = csv.reader(fh)
        header = next(reader)
    assert header == ["tag_name", "data_type", "scope", "written_by", "description"]
