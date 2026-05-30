"""Tests for the GitHub Actions pipeline generator."""

from __future__ import annotations

from plc_workflows_mpc.sdlc import PipelineConfig, generate_github_workflow, generate_pipeline


def test_default_workflow_has_expected_skeleton():
    yaml = generate_github_workflow()
    assert "name: PLC Code CI" in yaml
    assert "on:" in yaml
    assert "pull_request:" in yaml
    assert "jobs:" in yaml
    assert "plc-ci:" in yaml
    assert "actions/checkout@v4" in yaml
    assert "actions/setup-python@v5" in yaml
    assert "python-version: '3.12'" in yaml
    assert "pip install plc-workflows-mpc" in yaml
    assert "python -m plc_workflows_mpc.sdlc validate" in yaml
    assert "python -m plc_workflows_mpc.sdlc roundtrip" in yaml
    # Diff step gated on pull_request.
    assert "github.event_name == 'pull_request'" in yaml
    assert "python -m plc_workflows_mpc.sdlc diff" in yaml


def test_python_version_is_configurable():
    yaml = generate_github_workflow(PipelineConfig(python_version="3.13"))
    assert "python-version: '3.13'" in yaml


def test_disabling_steps_removes_them():
    yaml = generate_github_workflow(
        PipelineConfig(run_lint=False, run_roundtrip_check=False, run_diff_report=False)
    )
    assert "validate" not in yaml
    assert "roundtrip" not in yaml
    assert "structural diff" not in yaml


def test_l5x_glob_appears_in_steps():
    yaml = generate_github_workflow(PipelineConfig(l5x_glob="plc/**/*.L5X"))
    assert "plc/**/*.L5X" in yaml


def test_extra_steps_are_appended():
    yaml = generate_github_workflow(
        PipelineConfig(
            extra_steps=(
                {"name": "Run unit tests", "run": "pytest -v"},
                {
                    "name": "Upload report",
                    "uses": "actions/upload-artifact@v4",
                    "with": {"path": "report.txt"},
                },
            ),
        )
    )
    assert "Run unit tests" in yaml
    assert "pytest -v" in yaml
    assert "Upload report" in yaml
    assert "actions/upload-artifact@v4" in yaml
    assert "path: report.txt" in yaml


def test_generate_pipeline_dict_facade():
    yaml = generate_pipeline({"name": "Hello PLC", "python_version": "3.12"})
    assert "name: Hello PLC" in yaml


def test_generate_pipeline_ignores_unknown_keys():
    yaml = generate_pipeline({"name": "X", "totally_unknown_key": True})
    assert "name: X" in yaml
