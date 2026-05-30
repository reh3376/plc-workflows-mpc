"""Tests for the SDLC CLI (``python -m plc_workflows_mpc.sdlc``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plc_workflows_mpc.sdlc.cli import main

_GOOD = b"""<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<RSLogix5000Content SchemaRevision="1.0">
  <Controller Name="C">
    <Tags>
      <Tag Name="A" DataType="BOOL"/>
    </Tags>
  </Controller>
</RSLogix5000Content>
"""

_BAD = b"<?xml version='1.0'?><Other/>"


@pytest.fixture
def good_l5x(tmp_path: Path) -> Path:
    path = tmp_path / "good.L5X"
    path.write_bytes(_GOOD)
    return path


@pytest.fixture
def bad_l5x(tmp_path: Path) -> Path:
    path = tmp_path / "bad.L5X"
    path.write_bytes(_BAD)
    return path


def test_validate_ok(good_l5x: Path, capsys: pytest.CaptureFixture[str]):
    rc = main(["validate", str(good_l5x)])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_validate_failure(bad_l5x: Path):
    rc = main(["validate", str(bad_l5x)])
    assert rc == 1


def test_roundtrip_ok(good_l5x: Path):
    rc = main(["roundtrip", str(good_l5x)])
    assert rc == 0


def test_to_json_creates_sibling(good_l5x: Path):
    rc = main(["to-json", str(good_l5x)])
    assert rc == 0
    assert (good_l5x.with_suffix(good_l5x.suffix + ".json")).exists()


def test_to_l5x_round_trip(good_l5x: Path, tmp_path: Path):
    assert main(["to-json", str(good_l5x)]) == 0
    json_path = good_l5x.with_suffix(good_l5x.suffix + ".json")
    # Strip ".json" → ".L5X" target.
    assert main(["to-l5x", str(json_path)]) == 0
    # Output sits next to the JSON, with ".L5X" suffix.
    assert json_path.with_suffix("").exists()


def test_diff_emits_changes(good_l5x: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    other = tmp_path / "other.L5X"
    other.write_bytes(_GOOD.replace(b'Name="C"', b'Name="X"'))
    rc = main(["diff", str(good_l5x), str(other)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "~" in out  # changed marker


def test_unknown_subcommand_errors():
    with pytest.raises(SystemExit):
        main(["nonsense"])
