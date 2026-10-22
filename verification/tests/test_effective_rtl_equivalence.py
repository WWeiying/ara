"""Tests for the overlay-to-integrated HDL input audit."""

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "probes/audit_effective_rtl_equivalence.py"
SPEC = importlib.util.spec_from_file_location("audit_effective_rtl_equivalence", SCRIPT)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


def test_overlay_replacement_and_changed_source(tmp_path):
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    files = {
        "hardware/src/vlsu/vldu.sv": "old vldu",
        "hardware/src/vlsu/vstu.sv": "old vstu",
        "hardware/src/masku/masku.sv": "old masku",
        "hardware/src/ara.sv": "common",
        **{key: f"replacement {target}" for key, target in
           audit_module.REPLACEMENTS.items()},
    }
    old_manifest = []
    for key, value in files.items():
        path = old_root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="ascii")
        old_manifest.append({"path": str(path), "sha256": audit_module.digest(path)})
    new_manifest = []
    for target in audit_module.REPLACEMENTS.values():
        source = next(key for key, value in audit_module.REPLACEMENTS.items()
                      if value == target)
        files[target] = files[source]
    for key in ("hardware/src/vlsu/vldu.sv", "hardware/src/vlsu/vstu.sv",
                "hardware/src/masku/masku.sv", "hardware/src/ara.sv"):
        path = new_root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[key], encoding="ascii")
        new_manifest.append({"path": str(path), "sha256": audit_module.digest(path)})
    old_path = tmp_path / "old.json"
    new_path = tmp_path / "new.json"
    old_path.write_text(json.dumps({"repo_root": str(old_root), "files": old_manifest}),
                        encoding="utf-8")
    new_path.write_text(json.dumps({"repo_root": str(new_root), "files": new_manifest}),
                        encoding="utf-8")
    old_config = tmp_path / "old.conf"
    new_config = tmp_path / "new.conf"
    old_config.write_text("nr_lanes=4\n", encoding="ascii")
    new_config.write_text("nr_lanes=4\n", encoding="ascii")

    result = audit_module.audit(old_path, new_path, old_config, new_config)
    assert result["status"] == "PASS"
    assert result["hdl_file_count"] == 4

    changed = new_root / "hardware/src/ara.sv"
    changed.write_text("changed", encoding="ascii")
    new_manifest[-1]["sha256"] = audit_module.digest(changed)
    new_path.write_text(json.dumps({"repo_root": str(new_root), "files": new_manifest}),
                        encoding="utf-8")
    result = audit_module.audit(old_path, new_path, old_config, new_config)
    assert result["status"] == "FAIL"
    assert result["changed"] == ["hardware/src/ara.sv"]
