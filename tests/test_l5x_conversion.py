"""Tests for L5X ↔ JSON conversion."""

from __future__ import annotations

from pathlib import Path

import pytest

from plc_workflows_mpc.sdlc import (
    L5xDiffEntry,
    convert_json_file_to_l5x,
    convert_l5x_file_to_json,
    dict_to_l5x,
    l5x_diff,
    l5x_to_dict,
    read_json,
    validate_l5x,
    write_json,
)
from plc_workflows_mpc.sdlc.conversion import _COMMENT_TAG

_SAMPLE_L5X = b"""<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="33.00">
  <!-- generated for test -->
  <Controller Name="MyController" ProcessorType="1756-L83E">
    <Tags>
      <Tag Name="MPC_Enable" TagType="Base" DataType="BOOL"/>
      <Tag Name="MPC_Temp_SP" TagType="Base" DataType="REAL"/>
    </Tags>
  </Controller>
</RSLogix5000Content>
"""


# ── dict round-trip ---------------------------------------------------------


def test_l5x_to_dict_root():
    payload = l5x_to_dict(_SAMPLE_L5X)
    assert payload["tag"] == "RSLogix5000Content"
    assert payload["attrib"]["SchemaRevision"] == "1.0"
    # First non-whitespace child should be the comment, then the Controller.
    comment_children = [c for c in payload["children"] if c["tag"] == _COMMENT_TAG]
    assert len(comment_children) == 1
    assert "generated for test" in (comment_children[0]["text"] or "")


def test_round_trip_preserves_structure():
    payload = l5x_to_dict(_SAMPLE_L5X)
    rendered = dict_to_l5x(payload)
    re_parsed = l5x_to_dict(rendered)
    assert payload == re_parsed


def test_dict_to_l5x_requires_tag():
    with pytest.raises(ValueError):
        dict_to_l5x({"attrib": {}})


def test_tag_attributes_round_trip():
    payload = l5x_to_dict(_SAMPLE_L5X)
    controller = next(c for c in payload["children"] if c["tag"] == "Controller")
    tags_node = next(c for c in controller["children"] if c["tag"] == "Tags")
    tag_names = [t["attrib"]["Name"] for t in tags_node["children"] if t["tag"] == "Tag"]
    assert tag_names == ["MPC_Enable", "MPC_Temp_SP"]


# ── Validation --------------------------------------------------------------


def test_validate_l5x_accepts_well_formed():
    ok, reason = validate_l5x(_SAMPLE_L5X)
    assert ok is True
    assert reason is None


def test_validate_l5x_rejects_wrong_root():
    bad = b"<?xml version='1.0'?><NotL5X/>"
    ok, reason = validate_l5x(bad)
    assert ok is False
    assert reason is not None
    assert "RSLogix5000Content" in reason


def test_validate_l5x_rejects_unparseable():
    ok, reason = validate_l5x(b"<not valid xml")
    assert ok is False
    assert reason is not None


# ── File helpers ------------------------------------------------------------


def test_file_round_trip(tmp_path: Path):
    l5x_path = tmp_path / "sample.L5X"
    l5x_path.write_bytes(_SAMPLE_L5X)
    json_path = tmp_path / "sample.L5X.json"
    convert_l5x_file_to_json(l5x_path, json_path)
    assert json_path.exists()

    out_l5x = tmp_path / "out" / "rebuilt.L5X"
    convert_json_file_to_l5x(json_path, out_l5x)
    assert out_l5x.exists()
    assert l5x_to_dict(out_l5x.read_bytes()) == l5x_to_dict(_SAMPLE_L5X)


def test_write_and_read_json(tmp_path: Path):
    payload = l5x_to_dict(_SAMPLE_L5X)
    path = tmp_path / "out.json"
    write_json(payload, path)
    assert read_json(path) == payload


def test_read_json_rejects_non_object(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("[1, 2, 3]")
    with pytest.raises(ValueError):
        read_json(path)


# ── Structural diff ---------------------------------------------------------


def _modify_attribute(xml: bytes, *, name: str, value: str) -> bytes:
    payload = l5x_to_dict(xml)
    controller = next(c for c in payload["children"] if c["tag"] == "Controller")
    controller["attrib"][name] = value
    return dict_to_l5x(payload)


def test_diff_detects_attribute_change():
    modified = _modify_attribute(_SAMPLE_L5X, name="Name", value="OtherController")
    entries = l5x_diff(_SAMPLE_L5X, modified)
    assert any(
        isinstance(e, L5xDiffEntry) and e.op == "changed" and e.path.endswith("@Name")
        for e in entries
    )


def test_diff_detects_added_attribute():
    modified = _modify_attribute(_SAMPLE_L5X, name="Description", value="added")
    entries = l5x_diff(_SAMPLE_L5X, modified)
    assert any(e.op == "added" and "@Description" in e.path for e in entries)


def test_diff_detects_added_child():
    payload = l5x_to_dict(_SAMPLE_L5X)
    controller = next(c for c in payload["children"] if c["tag"] == "Controller")
    controller["children"].append(
        {"tag": "Description", "attrib": {}, "text": "added node", "tail": None, "children": []}
    )
    entries = l5x_diff(_SAMPLE_L5X, payload)
    assert any(e.op == "added" for e in entries)


def test_diff_empty_for_identical_documents():
    assert l5x_diff(_SAMPLE_L5X, _SAMPLE_L5X) == []
