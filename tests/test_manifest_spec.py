"""Guard that manifest.json and the FACTS spec stay consistent."""

import json
from pathlib import Path

_MANIFEST = Path(__file__).resolve().parents[1] / "src" / "plc_workflows_mpc" / "manifest.json"
_SPEC = Path(__file__).resolve().parents[1] / "specs" / "plc-workflows-mpc.facts.json"


def test_manifest_is_valid_json():
    manifest = json.loads(_MANIFEST.read_text())
    assert manifest["adapter_id"] == "plc-workflows-mpc"
    assert manifest["tier"] == "OT"


def test_spec_is_valid_json():
    spec = json.loads(_SPEC.read_text())
    assert spec["specification_type"] == "adapter_registration"
    assert spec["integrity"]["hash_state"] == "pending_review"


def test_manifest_and_spec_agree():
    manifest = json.loads(_MANIFEST.read_text())
    spec = json.loads(_SPEC.read_text())["adapter"]
    assert manifest["adapter_id"] == spec["adapter_id"]
    assert manifest["version"] == spec["version"]
    assert manifest["tier"] == spec["tier"]
    assert manifest["protocol"] == spec["protocol"]
    assert manifest["capabilities"] == spec["capabilities"]
