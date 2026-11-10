"""Host-only canonical CPU-fix delivery proof; never modify shared dependencies."""
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile

import pytest

from ara_verify.dependencies import locked_dependencies
from ara_verify.dependency_patches import (
    PatchError, apply_patch_bundle, canonical_diff, git, load_registry, patch_state,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
CHECKPOINT = "9af19508de139641ea561ccdbd3114eba4007c6e"
REVISION = "b29fd3cf906e7f4c71da4c2f46451c4c60a4487f"
PATCH_NAME = "cva6-local-fixes.patch"
BASE_SHA = "3853ab475d5e20887a5a086cbdca6afdf7bfa3b5e178e99bf48ea3b05551dfb2"
SUCCESSOR_SHA = "4afb780061813ca90b19e94aa6b552ac0c11df7ac57a33bf594a9392468dd3b8"
PRE_SHA = "bf59bfa36960ec6227cb49d86e60f8b8f9507590f64ecfafffa9d8d8f94abb60"
POST_SHA = "ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249"
GATE = OUT / "resident_pv_commit_dirty_20261110_03"
OVERLAY = GATE / "inputs/test/accel_dirty_retirement.patch"
OVERLAY_SHA = "b4fe150d85074ce51acbddcb88600f359503b60427337919df3350f1acb13c00"
GATE_SHA = "2b297b1738ba1aea7e539a83ac6ade6dfd624168590d804fb211dec285b4872d"
TARGET = "core/commit_stage.sv"
MARKER = b"diff --git a/core/commit_stage.sv b/core/commit_stage.sv\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Inputs:
    archive: bytes
    baseline: bytes
    overlay: bytes
    current: bytes
    specification: dict
    objects: Path


@pytest.fixture(scope="module")
def inputs():
    source = ROOT / "hardware/deps/cva6"
    registry = load_registry(ROOT)
    specification = registry["cva6"]
    locked = {dep.name: dep.revision for dep in locked_dependencies(ROOT / "Bender.lock")}
    assert locked["cva6"] == specification["revision"] == REVISION
    assert specification["patch"] == PATCH_NAME
    baseline = git(ROOT, "show", f"{CHECKPOINT}:verification/patches/{PATCH_NAME}")
    assert digest(baseline) == BASE_SHA
    assert MARKER not in baseline
    current_path = ROOT / "verification/patches" / PATCH_NAME
    current = current_path.read_bytes()
    assert digest(current) == specification["sha256"]
    assert digest(current) in (BASE_SHA, SUCCESSOR_SHA), "Unreviewed delivery bundle"
    assert digest(OVERLAY.read_bytes()) == OVERLAY_SHA
    assert digest((GATE / "report.json").read_bytes()) == GATE_SHA
    report = json.loads((GATE / "report.json").read_text())
    assert report["state"] == "PASS" and report["post_pins_match"] and report["post_image_match"]
    assert report["overlay"]["dependency_revision"] == REVISION
    assert report["overlay"]["before_sha256"] == PRE_SHA
    assert report["overlay"]["after_sha256"] == POST_SHA
    assert report["overlay"]["patch_sha256"] == OVERLAY_SHA
    # Only immutable objects are imported. No shared working-tree/index content
    # is used to construct the temporary dependency.
    archive = git(source, "archive", REVISION)
    objects = Path(git(source, "rev-parse", "--path-format=absolute",
                       "--git-path", "objects").decode().strip())
    watched = (current_path, ROOT / "verification/patches/dependencies.json",
               ROOT / "verification/ara_verify/dependency_patches.py",
               ROOT / "verification/tests/test_dependency_patches.py",
               OVERLAY, GATE / "report.json", source / TARGET)
    before = {path: digest(path.read_bytes()) for path in watched}
    yield Inputs(archive, baseline, OVERLAY.read_bytes(), current, specification, objects)
    assert before == {path: digest(path.read_bytes()) for path in watched}


def locked_tree(root, inputs):
    tree = root / "hardware/deps/cva6"
    tree.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(inputs.archive)) as archive:
        assert archive.pax_headers.get("comment") == REVISION
        for entry in archive.getmembers():
            path = Path(entry.name)
            assert not path.is_absolute() and ".." not in path.parts
            assert entry.isfile() or entry.isdir() or entry.issym()
            if entry.issym():
                assert (tree / path.parent / entry.linkname).resolve().is_relative_to(tree)
        archive.extractall(tree)
    git(tree, "init", "-q")
    git(tree, "update-ref", "HEAD", REVISION)
    git(tree, "read-tree", REVISION)
    assert canonical_diff(tree) == b""
    assert digest((tree / TARGET).read_bytes()) == PRE_SHA
    return tree


def temporary_registry(root, content, inputs):
    directory = root / "verification/patches"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / PATCH_NAME).write_bytes(content)
    specification = dict(inputs.specification, sha256=digest(content))
    (directory / "dependencies.json").write_text(json.dumps(
        {"schema_version": 1, "patches": {"cva6": specification}}, sort_keys=True) + "\n")


def apply_file(tree, path):
    git(tree, "apply", "--check", str(path))
    git(tree, "apply", str(path))


@pytest.fixture
def successor(tmp_path, monkeypatch, inputs):
    for key in tuple(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", str(inputs.objects))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    # This is a disposable archive reconstruction, not a registered Git worktree
    # or a development checkout. The shared object database is read-only.
    with tempfile.TemporaryDirectory(dir=tmp_path, prefix="locked-archive-") as directory:
        root = Path(directory)
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(root))
        tree = locked_tree(root, inputs)
        temporary_registry(root, inputs.baseline, inputs)
        assert patch_state(root, "cva6", tree, REVISION) == "missing"
        assert apply_patch_bundle(root, "cva6", tree, REVISION) == "applied"
        assert canonical_diff(tree) == inputs.baseline
        assert digest((tree / TARGET).read_bytes()) == PRE_SHA
        overlay = root / "sealed-overlay.patch"
        overlay.write_bytes(inputs.overlay)
        apply_file(tree, overlay)
        assert digest((tree / TARGET).read_bytes()) == POST_SHA
        candidate = canonical_diff(tree)
        assert digest(candidate) == SUCCESSOR_SHA
        assert candidate.count(MARKER) == 1
        start = candidate.index(MARKER)
        end = candidate.find(b"diff --git ", start + len(MARKER))
        assert end > start
        assert candidate[:start] + candidate[end:] == inputs.baseline
        temporary_registry(root, candidate, inputs)
        assert patch_state(root, "cva6", tree, REVISION) == "applied"
        yield root, tree, candidate


def test_locked_archive_overlay_and_current_or_promoted_registry(successor, inputs, record_property):
    root, tree, candidate = successor
    if digest(inputs.current) == BASE_SHA:
        assert inputs.current == inputs.baseline
        record_property("registry_phase", "pre-promotion; temporary successor validated")
    else:
        assert inputs.current == candidate
        record_property("registry_phase", "promoted registry validated")
    assert load_registry(root)["cva6"]["revision"] == REVISION
    assert digest((tree / TARGET).read_bytes()) == POST_SHA
    record_property("baseline_cpu_sha256", PRE_SHA)
    record_property("successor_cpu_sha256", POST_SHA)
    record_property("canonical_bundle_sha256", digest(candidate))


def test_direct_apply_and_idempotent_admission(successor, inputs):
    root, _, candidate = successor
    direct = root / "direct"
    tree = locked_tree(direct, inputs)
    temporary_registry(direct, candidate, inputs)
    assert patch_state(direct, "cva6", tree, REVISION) == "missing"
    for _ in range(2):
        assert apply_patch_bundle(direct, "cva6", tree, REVISION) == "applied"
        assert canonical_diff(tree) == candidate
        assert digest((tree / TARGET).read_bytes()) == POST_SHA
    git(tree, "add", TARGET)
    assert patch_state(direct, "cva6", tree, REVISION) == "applied"


@pytest.mark.parametrize("kind", ("expected_revision", "registry_revision", "checkout"))
def test_wrong_base_rejected_without_modification(successor, kind):
    root, tree, _ = successor
    expected = REVISION
    message = "expected"
    if kind == "expected_revision":
        expected = "0" * 40
    elif kind == "registry_revision":
        path = root / "verification/patches/dependencies.json"
        data = json.loads(path.read_text())
        data["patches"]["cva6"]["revision"] = "0" * 40
        path.write_text(json.dumps(data))
        message = "Bender.lock"
    else:
        git(tree, "update-ref", "HEAD", REVISION + "^")
    before = canonical_diff(tree)
    with pytest.raises(PatchError, match=message):
        apply_patch_bundle(root, "cva6", tree, expected)
    assert canonical_diff(tree) == before
    assert digest((tree / TARGET).read_bytes()) == POST_SHA


@pytest.mark.parametrize("kind", ("tracked", "staged", "untracked"))
def test_extraneous_changes_rejected_without_overwrite(successor, kind):
    root, tree, _ = successor
    path = tree / ("unexpected.sv" if kind == "untracked" else "core/acc_dispatcher.sv")
    content = (path.read_bytes() if path.exists() else b"") + b"\n// unrelated host-test delta\n"
    path.write_bytes(content)
    if kind == "staged":
        git(tree, "add", str(path.relative_to(tree)))
    before = canonical_diff(tree)
    with pytest.raises(PatchError, match="untracked" if kind == "untracked" else "differ"):
        apply_patch_bundle(root, "cva6", tree, REVISION)
    assert canonical_diff(tree) == before and path.read_bytes() == content
    assert digest((tree / TARGET).read_bytes()) == POST_SHA


def test_old_bundle_tree_is_not_implicitly_upgraded(successor, inputs):
    root, _, candidate = successor
    legacy = root / "legacy"
    tree = locked_tree(legacy, inputs)
    baseline = legacy / "baseline.patch"
    baseline.write_bytes(inputs.baseline)
    apply_file(tree, baseline)
    temporary_registry(legacy, candidate, inputs)
    with pytest.raises(PatchError, match="differ"):
        apply_patch_bundle(legacy, "cva6", tree, REVISION)
    assert canonical_diff(tree) == inputs.baseline
    assert digest((tree / TARGET).read_bytes()) == PRE_SHA


def test_verbatim_overlay_append_is_not_canonical(successor, inputs):
    root, tree, candidate = successor
    concatenated = inputs.baseline + inputs.overlay
    assert concatenated != candidate
    temporary_registry(root, concatenated, inputs)
    with pytest.raises(PatchError, match="differ"):
        apply_patch_bundle(root, "cva6", tree, REVISION)
    assert canonical_diff(tree) == candidate
    assert digest((tree / TARGET).read_bytes()) == POST_SHA
