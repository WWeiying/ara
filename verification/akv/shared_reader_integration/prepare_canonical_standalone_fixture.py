#!/usr/bin/env python3
"""Copy a reviewed storage snapshot into a fresh canonical-layout test fixture only."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
from compose_canonical_standalone import digest
from prepare_storage import validate_snapshot

HERE = Path(__file__).resolve().parent
MAPPING = {
    "qbs_akv_shared_reader.sv": "hardware/src/vlsu/qbs_akv_shared_reader.sv",
    "akv_legacy_repacker.sv": "hardware/src/vlsu/akv/akv_legacy_repacker.sv",
    "akv_q_store.sv": "hardware/src/vlsu/akv/akv_q_store.sv",
    "akv_unified_context.sv": "hardware/src/vlsu/akv/akv_unified_context.sv",
    "shared_reader_types.svh": "hardware/include/shared_reader_types.svh",
    "vlsu_shared_reader.svh": "hardware/include/vlsu_shared_reader.svh",
    "admission_assertions.svh": "hardware/include/admission_assertions.svh",
}


def map_filelist(text, snapshot, output):
    lines = []
    for raw in text.splitlines():
        token = raw.strip()
        if not token or token.startswith(("//", "#", "+define+")):
            lines.append(raw)
            continue
        include = token.startswith("+incdir+")
        path = Path(token[len("+incdir+"):] if include else token)
        if path == snapshot / "support" and include:
            mapped = output / "hardware/include"
        elif path.is_relative_to(snapshot / "source"):
            mapped = output / path.relative_to(snapshot / "source")
        elif path.parent == snapshot / "support" and path.name in MAPPING and not include:
            mapped = output / MAPPING[path.name]
        else:
            raise ValueError("Unmapped snapshot source/include: " + token)
        lines.append(("+incdir+" if include else "") + str(mapped))
    return "\n".join(lines) + "\n"


def prepare(snapshot, output):
    report = validate_snapshot(snapshot)
    if output.is_relative_to(snapshot):
        raise ValueError("Fixture output must be outside the frozen snapshot")
    manifest = snapshot / "manifest.json"
    actual_sources = {str(p) for p in (snapshot / "source").rglob("*") if p.is_file()}
    if actual_sources != set(report["source_mapping"].values()):
        raise ValueError("Unexpected snapshot source inventory")
    own = [HERE / name for name in ("prepare_canonical_standalone_fixture.py",
           "compose_canonical_standalone.py", "compose_standalone.py",
           "test_canonical_standalone.py", "CANONICAL_STANDALONE_README.md")]
    identity = {**report["input_pins"], **report["artifact_pins"], str(manifest): digest(manifest),
                **{str(p): digest(p) for p in own}, str(Path(sys.executable).resolve()): digest(sys.executable)}
    # copytree refuses an existing output. Never move/symlink a consumed snapshot.
    shutil.copytree(snapshot / "source", output, symlinks=False)
    support = {}
    for name, relative in MAPPING.items():
        source, target = snapshot / "support" / name, output / relative
        if target.exists() or report["artifact_pins"].get(str(source)) != digest(source):
            raise ValueError("Support mapping collision or unpinned input: " + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        support[str(target)] = {"source": str(source), "sha256": digest(source)}
    filelist = output / "canonical_sources.f"
    filelist.write_text(map_filelist(Path(report["compile_filelist"]).read_text(), snapshot, output))
    for source, copy in report["source_mapping"].items():
        source_copy = Path(copy)
        target = output / source_copy.relative_to(snapshot / "source")
        if digest(source_copy) != digest(target):
            raise ValueError("Snapshot source copy mismatch: " + source)
    validate_snapshot(snapshot)
    for path, expected in identity.items():
        if digest(path) != expected:
            raise ValueError("Fixture input drift: " + path)
    receipt = {"state": "CANONICAL_LAYOUT_FIXTURE_NOT_PROMOTED", "source_root": str(output),
               "snapshot_manifest": str(manifest), "snapshot_sha256": digest(manifest),
               "filelist": str(filelist), "support_mapping": support, "input_pins": identity,
               "artifact_pins": {str(p): digest(p) for p in output.rglob("*") if p.is_file()},
               "bender_metadata_is_unchanged_snapshot_copy": True,
               "source_list_is_explicit_not_regenerated_by_bender": True,
               "production_promoted": False, "eda_executed": False}
    path = output / "canonical-layout-receipt.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = prepare(args.snapshot.resolve(strict=True), args.output.resolve())
    print("CANONICAL_LAYOUT_FIXTURE_NOT_PROMOTED receipt=" + str(path) + " sha256=" + digest(path))
