from pathlib import Path

import pytest

from cva6.run_wt_inval_collision import classify, extract, original_adapter, cases


def test_baseline_is_exact_original():
    root = Path(__file__).resolve().parents[2]
    source = root / "hardware/deps/cva6/core/cache_subsystem/wt_axi_adapter.sv"
    old = original_adapter(source.read_text())
    assert "axi_rd_rdy        = ~invalidate;" in old
    assert "axi_rd_rdy        = ~invalidate & ~inval_valid_i;" not in old


def test_unknown_baseline_change_rejected():
    root = Path(__file__).resolve().parents[2]
    text = (root / "hardware/deps/cva6/core/cache_subsystem/wt_axi_adapter.sv").read_text()
    with pytest.raises(ValueError, match="exact pre-repair"):
        original_adapter(text + "\n// unrelated modification\n")


def test_vcs_zero_exit_fatal_is_not_pass():
    text = "COLLISION_RESULT reads=4\nINVAL_READ_PASS collide=3\nFatal: lost response\n"
    assert not classify(text, {"returncode": 0}, "repaired", (3, 0, 1, 0))["accepted"]


@pytest.mark.parametrize("text,receipt", [
    ("INVAL_READ_PASS collide=3\n", {"returncode": 0}),
    ("COLLISION_RESULT reads=4\nINVAL_READ_PASS collide=2\n", {"returncode": 0}),
    ("COLLISION_RESULT reads=4\nINVAL_READ_PASS collide=3\n", {"returncode": 1}),
    ("COLLISION_RESULT reads=4\nINVAL_READ_PASS collide=3\n", {"returncode": 0, "timeout": True}),
    ("COLLISION_RESULT reads=4\nINVAL_READ_PASS collide=3\nINVAL_READ_PASS collide=3\n", {"returncode": 0}),
])
def test_incomplete_or_conflicting_success_rejected(text, receipt):
    assert not classify(text, receipt, "repaired", (3, 0, 1, 0))["accepted"]


def test_expected_failure_must_be_specific():
    row = (3, 0, 1, 0)
    assert classify("Fatal: READ_COMPLETION_LOST\n", {"returncode": 0}, "baseline", row)["accepted"]
    assert not classify("Fatal: TEST_TIMEOUT\n", {"returncode": 1}, "baseline", row)["accepted"]
    assert not classify("Fatal: READ_COMPLETION_LOST\n", {"returncode": -1, "timeout": True}, "baseline", row)["accepted"]


def test_actual_interface_extraction_handles_nested_struct():
    source = "parameter type thing_t = struct packed { logic a; struct packed { logic b; } nested; },"
    assert extract(source, "thing_t") == "typedef struct packed { logic a; struct packed { logic b; } nested; } thing_t;\n"
    with pytest.raises(ValueError):
        extract(source + source, "thing_t")


def test_matrix_includes_every_dcache_beat_and_b_overlap():
    rows = cases("repaired")
    assert len(rows) == 30 and len(set(rows)) == 30
    assert all((beat, 0, hold, b) in rows for beat in range(4)
               for hold in (1, 4) for b in (0, 1))
    assert (1, 1, 4, 0) in rows and (0, 2, 4, 0) in rows
