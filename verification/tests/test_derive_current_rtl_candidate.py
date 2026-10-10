"""The SoC handoff must fail closed on changed Ara include files."""

import hashlib

import pytest

from fpga.derive_current_rtl_candidate import audit_rtl_tree


def test_include_change_requires_explicit_expectation(tmp_path):
    frozen = tmp_path / "frozen"
    current = tmp_path / "current"
    frozen.mkdir()
    current.mkdir()
    (frozen / "ara_pkg.sv").write_text("typedef struct packed { logic is_load; } req_t;\n")
    (current / "ara_pkg.sv").write_text(
        "typedef struct packed { logic is_load; logic is_skip; } req_t;\n")

    with pytest.raises(ValueError, match="unreviewed Ara RTL changes"):
        audit_rtl_tree(frozen, current, frozenset(), frozenset())

    changed = audit_rtl_tree(frozen, current, frozenset({"ara_pkg.sv"}), frozenset())
    assert set(changed) == {"ara_pkg.sv"}
    assert changed["ara_pkg.sv"]["old_sha256"] == hashlib.sha256(
        (frozen / "ara_pkg.sv").read_bytes()).hexdigest()
    assert changed["ara_pkg.sv"]["new_sha256"] == hashlib.sha256(
        (current / "ara_pkg.sv").read_bytes()).hexdigest()


def test_include_inventory_change_is_rejected(tmp_path):
    frozen = tmp_path / "frozen"
    current = tmp_path / "current"
    frozen.mkdir()
    current.mkdir()
    (current / "new_pkg.sv").write_text("package new_pkg; endpackage\n")

    with pytest.raises(ValueError, match="Ara RTL file inventory differs"):
        audit_rtl_tree(frozen, current, frozenset(), frozenset())
