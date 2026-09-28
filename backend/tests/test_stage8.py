import json
from pathlib import Path

import pytest

from app import final_validation_service as s
from app import export_service


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "assets_root", lambda: tmp_path)
    monkeypatch.setattr(export_service, "assets_root", lambda: tmp_path)
    return tmp_path


def make_project(root: Path, with_export=True):
    pid = "a" * 32
    project = root / "projects" / pid
    project.mkdir(parents=True)
    (project / "source.blend").write_bytes(b"BLENDER")
    manifest = {
        "format": "bodiez-project", "format_version": 1, "project_id": pid, "name": "Teste Final", "created_at": 123,
        "source": {"kind": "customization_revision", "file_ref": "source.blend"},
        "body": {"editable": True, "values": {"height": 1.05}, "bindings": {}}, "poses": {}, "animation": {},
        "editability": {"authoritative_format": "blend", "body_parameters_recorded": True, "pose_data_recorded": False, "animation_data_recorded": False, "interchange_exports_retain_bodiez_control_semantics": False},
    }
    (project / "project.bodiez.json").write_text(json.dumps(manifest), encoding="utf-8")
    eid = None
    if with_export:
        eid = "b" * 32
        export = project / "exports" / eid
        export.mkdir(parents=True)
        (export / "character.glb").write_bytes(b"glTF")
        (export / "character.png").write_bytes(b"png")
        (export / "request.json").write_text(json.dumps({"formats": ["glb", "png"]}), encoding="utf-8")
        (export / "report.json").write_text(json.dumps({"warnings": [{"message": "Aviso da Etapa 7"}]}), encoding="utf-8")
    return pid, eid


def test_lists_projects_and_exports(root):
    pid, eid = make_project(root)
    rows = s.list_validation_targets()
    assert rows[0]["project_id"] == pid
    assert rows[0]["exports"][0]["export_id"] == eid
    assert rows[0]["exports"][0]["files"]["glb"] is True


def test_run_preserves_confined_paths_and_project_contract(root):
    pid, eid = make_project(root)
    run = s.create_validation_run(pid, eid)
    request = json.loads(run.request.read_text())
    assert Path(request["source_blend"]).name == "source.blend"
    assert Path(request["export_files"]["glb"]).parent.name == eid
    assert any(c["key"] == "relative_reference" and c["status"] == "pass" for c in request["project_checks"])


def test_invalid_ids_are_rejected(root):
    make_project(root)
    with pytest.raises(s.FinalValidationError): s.create_validation_run("../bad")
    with pytest.raises(s.FinalValidationError): s.create_validation_run("a" * 32, "../bad")


def test_manifest_inconsistency_becomes_warning(root):
    pid, _ = make_project(root, with_export=False)
    manifest_path = root / "projects" / pid / "project.bodiez.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["editability"]["body_parameters_recorded"] = False
    manifest_path.write_text(json.dumps(manifest))
    run = s.create_validation_run(pid)
    request = json.loads(run.request.read_text())
    item = next(c for c in request["project_checks"] if c["key"] == "body_contract")
    assert item["status"] == "warn"


def test_report_verdict_and_limitations(root):
    pid, eid = make_project(root)
    run = s.create_validation_run(pid, eid)
    blender = {
        "scene": [{"key": "reopen", "label": "Reabrir", "status": "pass", "evidence": "ok"}],
        "deformation": [{"key": "knee", "label": "Joelho", "status": "pass", "evidence": "ok"}],
        "exports": [{"key": "glb", "label": "GLB", "status": "warn", "evidence": "revisar"}],
        "resources": [], "metrics": {"height": 1.8}, "limitations": ["Limitação medida"],
    }
    report = s.build_final_report(run, blender)
    assert report["verdict"] == "pass_with_warnings"
    assert report["summary"]["failures"] == 0
    assert "Aviso da Etapa 7" in report["limitations"]
    assert "Limitação medida" in report["limitations"]


def test_failure_blocks_validation(root):
    pid, _ = make_project(root, with_export=False)
    run = s.create_validation_run(pid)
    report = s.build_final_report(run, {"scene": [{"key": "mesh", "label": "Malha", "status": "fail", "evidence": "ausente"}]})
    assert report["verdict"] == "blocked"
    assert report["summary"]["failures"] == 1


def test_selected_export_is_tied_to_project(root):
    pid, eid = make_project(root)
    request_path = root / "projects" / pid / "exports" / eid / "request.json"
    request_path.write_text(json.dumps({"project_id": "c" * 32, "formats": ["glb", "png"]}))
    run = s.create_validation_run(pid, eid)
    data = json.loads(run.request.read_text())
    lineage = next(c for c in data["project_checks"] if c["key"] == "export_lineage")
    assert lineage["status"] == "fail"


def test_stage7_warning_affects_verdict(root):
    pid, eid = make_project(root)
    run = s.create_validation_run(pid, eid)
    report = s.build_final_report(run, {"scene": [{"key": "reopen", "label": "Reabrir", "status": "pass", "evidence": "ok"}]})
    assert report["verdict"] == "pass_with_warnings"
    assert any(c["key"].startswith("stage7_warning_") and c["status"] == "warn" for c in report["checks"])
