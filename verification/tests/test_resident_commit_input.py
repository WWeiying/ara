import hashlib
import json
from pathlib import Path
import runpy

import pytest


CHECK = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                           "hardware/scripts/akv/check_resident_commit_input.py"))["check"]


@pytest.fixture
def inputs(tmp_path):
    src = tmp_path / "core/commit_stage.sv"
    src.parent.mkdir()
    src.write_bytes(b"fixed")
    oid = hashlib.sha1(b"blob 5\0fixed").hexdigest()
    bundle = tmp_path / "cva6.patch"
    bundle.write_text(f"diff --git a/core/commit_stage.sv b/core/commit_stage.sv\n"
                      f"index {'0' * 40}..{oid} 100644\n")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"patches": {"cva6": {"patch": bundle.name,
                        "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest()}}}))
    listing = tmp_path / "sim.f"
    listing.write_text(f"// ignored/core/commit_stage.sv\n+incdir+/example\n{src}\n")
    return listing, registry, src, bundle, oid


def test_uses_listed_source(inputs):
    listing, registry, src, _, oid = inputs
    assert CHECK(listing, registry) == oid
    src.write_bytes(b"old")
    with pytest.raises(ValueError, match="expected registered"):
        CHECK(listing, registry)


@pytest.mark.parametrize("kind", ["empty", "relative", "duplicate", "registry_drift"])
def test_rejects_unverified_source(inputs, kind):
    listing, registry, src, bundle, _ = inputs
    if kind == "registry_drift":
        bundle.write_text("changed")
    else:
        listing.write_text({"empty": "", "relative": "core/commit_stage.sv\n",
                            "duplicate": f"{src}\n{src}\n"}[kind])
    with pytest.raises(ValueError):
        CHECK(listing, registry)
