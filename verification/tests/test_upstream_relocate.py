"""Reject missing evidence and unknown *normal* fetches, not expected page faults."""
import pytest
from cva6.run_upstream_relocate_20261009 import check_fetch


def sample():
    return ("[IFETCH_PAYLOAD] cycle=10 va=8000015c ex=1 cause=000000000000000c "
            "tval=000000008000015c unknown=1 legacy_warning=1\n"
            "[l1 dcache] reading invalid instructions: vaddr=8000015c, data=xxxxxxxx\n"
            "[IFETCH_PAYLOAD_END] normal=100 exceptions=1 unknown=1 legacy_warnings=1 errors=0\n")


def test_expected_exception_payload():
    assert check_fetch(sample(), {"linux_virtual_entry": 0x8000015c})["errors"] == 0


@pytest.mark.parametrize("before,after", [
    ("ex=1", "ex=0"), ("ex=1", "ex=x"), ("cause=000000000000000c", "cause=0000000000000002"),
    ("va=8000015c", "va=80000200"), ("tval=000000008000015c", "tval=0000000080000160"),
    ("errors=0", "errors=1"), ("unknown=1 legacy_warnings", "unknown=2 legacy_warnings"),
    ("normal=100", "normal=0"), ("[IFETCH_PAYLOAD_END]", "[TRUNCATED]"),
    ("[l1 dcache] reading invalid instructions:", "removed"),
])
def test_bad_evidence(before, after):
    with pytest.raises(ValueError):
        check_fetch(sample().replace(before, after), {"linux_virtual_entry": 0x8000015c})


def test_extra_warning_and_duplicate_summary():
    for extra in ("[l1 dcache] reading invalid instructions:\n", sample().splitlines()[-1] + "\n"):
        with pytest.raises(ValueError):
            check_fetch(sample() + extra, {"linux_virtual_entry": 0x8000015c})
