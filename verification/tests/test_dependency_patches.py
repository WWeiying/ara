import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ara_verify.dependency_patches import (
    PatchError, apply_patch_bundle, canonical_diff, ensure_submodules, git,
    load_registry, patch_state, snapshot, validate_submodules,
)


def init_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.name", "Verification test")
    git(path, "config", "user.email", "verification@example.invalid")
    (path / "rtl.sv").write_text("original\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "base")
    return git(path, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "root"
    dep = root / "hardware/deps/cva6"
    rev = init_repo(dep)
    (dep / "rtl.sv").write_text("reviewed fix\n")
    approved = canonical_diff(dep)
    directory = root / "verification/patches"
    directory.mkdir(parents=True)
    (directory / "cva6.patch").write_bytes(approved)
    spec = {"revision": rev, "patch": "cva6.patch",
            "sha256": hashlib.sha256(approved).hexdigest()}
    (directory / "dependencies.json").write_text(json.dumps(
        {"schema_version": 1, "patches": {"cva6": spec}}))
    return root, dep, rev


def test_exact_unstaged_and_staged_patch(bundle):
    root, dep, rev = bundle
    assert patch_state(root, "cva6", dep, rev) == "applied"
    git(dep, "add", "rtl.sv")
    assert patch_state(root, "cva6", dep, rev) == "applied"


def test_missing_patch_applied_idempotently(bundle):
    root, dep, rev = bundle
    (dep / "rtl.sv").write_text("original\n")
    assert patch_state(root, "cva6", dep, rev) == "missing"
    assert apply_patch_bundle(root, "cva6", dep, rev) == "applied"
    first = (dep / "rtl.sv").read_bytes()
    assert apply_patch_bundle(root, "cva6", dep, rev) == "applied"
    assert (dep / "rtl.sv").read_bytes() == first


@pytest.mark.parametrize("staged", [False, True])
def test_unknown_change_rejected_without_overwrite(bundle, staged):
    root, dep, rev = bundle
    (dep / "rtl.sv").write_text("user change\n")
    if staged:
        git(dep, "add", "rtl.sv")
    with pytest.raises(PatchError, match="differ"):
        apply_patch_bundle(root, "cva6", dep, rev)
    assert (dep / "rtl.sv").read_text() == "user change\n"


def test_untracked_input_rejected(bundle):
    root, dep, rev = bundle
    (dep / "extra.sv").write_text("unapproved\n")
    with pytest.raises(PatchError, match="untracked"):
        patch_state(root, "cva6", dep, rev)


def test_staged_extra_rejected(bundle):
    root, dep, rev = bundle
    (dep / "extra.sv").write_text("unapproved\n")
    git(dep, "add", "extra.sv")
    with pytest.raises(PatchError):
        patch_state(root, "cva6", dep, rev)


def test_hidden_staged_change_in_approved_file_rejected(bundle):
    root, dep, rev = bundle
    (dep / "rtl.sv").write_text("hidden index edit\n")
    git(dep, "add", "rtl.sv")
    (dep / "rtl.sv").write_text("reviewed fix\n")
    with pytest.raises(PatchError, match="mixed staged/unstaged"):
        patch_state(root, "cva6", dep, rev)


def test_new_staged_gitlink_cannot_hide_from_patch_diff(bundle):
    root, dep, rev = bundle
    git(dep, "update-index", "--add", "--cacheinfo", f"160000,{rev},unexpected")
    with pytest.raises(PatchError, match="index gitlinks"):
        patch_state(root, "cva6", dep, rev)


def test_tampered_patch_rejected(bundle):
    root, dep, rev = bundle
    with (root / "verification/patches/cva6.patch").open("ab") as output:
        output.write(b"\n")
    with pytest.raises(PatchError, match="digest"):
        patch_state(root, "cva6", dep, rev)


def test_revision_mismatch_rejected(bundle):
    root, dep, rev = bundle
    with pytest.raises(PatchError, match="expected"):
        patch_state(root, "cva6", dep, "a" * 40)


def test_manifest_base_must_match_lock(bundle):
    root, dep, rev = bundle
    manifest = root / "verification/patches/dependencies.json"
    data = json.loads(manifest.read_text())
    data["patches"]["cva6"]["revision"] = "a" * 40
    manifest.write_text(json.dumps(data))
    with pytest.raises(PatchError, match="Bender.lock"):
        patch_state(root, "cva6", dep, rev)


def test_linked_dependency_rejected(bundle):
    root, dep, rev = bundle
    link = root / "shared"
    link.symlink_to(dep, target_is_directory=True)
    with pytest.raises(PatchError, match="separate"):
        patch_state(root, "cva6", link, rev)


@pytest.mark.parametrize("filename", ["../outside.patch", "/tmp/outside.patch", ""])
def test_manifest_path_escape_rejected(bundle, filename):
    root, dep, rev = bundle
    manifest = root / "verification/patches/dependencies.json"
    data = json.loads(manifest.read_text())
    data["patches"]["cva6"]["patch"] = filename
    manifest.write_text(json.dumps(data))
    with pytest.raises(PatchError, match="filename"):
        load_registry(root)


def test_no_bundle_requires_clean_checkout(bundle):
    root, dep, rev = bundle
    with pytest.raises(PatchError, match="unapproved"):
        patch_state(root, "other", dep, rev)
    (dep / "rtl.sv").write_text("original\n")
    assert patch_state(root, "other", dep, rev) == "clean"


def test_snapshot_uses_lock_not_source_head_or_dirty_worktree(bundle, tmp_path):
    root, dep, rev = bundle
    source = tmp_path / "source"
    source_rev = init_repo(source)
    # Pin the source's first commit, then advance its HEAD and change its files.
    (source / "rtl.sv").write_text("new commit\n")
    git(source, "add", "rtl.sv")
    git(source, "commit", "-qm", "advance")
    (source / "rtl.sv").write_text("unfinished source edit\n")
    (root / "Bender.lock").write_text(
        "packages:\n  other:\n    revision: " + source_rev +
        "\n    source:\n      Git: example.invalid/repo\n")
    assert snapshot(root, "other", source) == "clean"
    target = root / "hardware/deps/other"
    assert git(target, "rev-parse", "HEAD").decode().strip() == source_rev
    assert (target / "rtl.sv").read_text() == "original\n"
    assert (source / "rtl.sv").read_text() == "unfinished source edit\n"
    assert snapshot(root, "other", source) == "clean"


@pytest.fixture
def nested(tmp_path):
    source = tmp_path / "child-source"
    revision = init_repo(source)
    parent = tmp_path / "parent"
    init_repo(parent)
    git(parent, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(source), "child")
    git(parent, "commit", "-qam", "pin child")
    with patch("ara_verify.dependency_patches.REQUIRED_SUBMODULES", {"test": ("child",)}):
        yield parent, source, revision


def test_nested_valid_pin(nested):
    parent, source, revision = nested
    validate_submodules(parent, "test")
    ensure_submodules(parent, "test")


def test_nested_dirt_rejected_without_overwrite(nested):
    parent, source, revision = nested
    child = parent / "child"
    (child / "rtl.sv").write_text("local nested edit\n")
    with pytest.raises(PatchError, match="dirty"):
        ensure_submodules(parent, "test")
    assert (child / "rtl.sv").read_text() == "local nested edit\n"


def test_nested_wrong_head_rejected(nested):
    parent, source, revision = nested
    child = parent / "child"
    git(child, "config", "user.name", "Test")
    git(child, "config", "user.email", "test@example.invalid")
    (child / "rtl.sv").write_text("new nested commit\n")
    git(child, "commit", "-qam", "advance")
    with pytest.raises(PatchError, match="expected"):
        ensure_submodules(parent, "test")
    git(parent, "add", "child")
    with pytest.raises(PatchError, match="index gitlink"):
        validate_submodules(parent, "test")


def test_nested_missing_and_materialize(nested, monkeypatch):
    parent, source, revision = nested
    git(parent, "submodule", "deinit", "-f", "--", "child")
    with pytest.raises(PatchError, match="not initialized"):
        validate_submodules(parent, "test")
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    ensure_submodules(parent, "test")
    validate_submodules(parent, "test")
