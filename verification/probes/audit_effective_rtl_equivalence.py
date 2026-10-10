"""Compare the HDL inputs of an overlay VCS image and its integrated image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HDL_SUFFIXES = {".sv", ".svh", ".v", ".vh"}
REPLACEMENTS = {
    "verification/probes/mask_bundle_candidate/vldu.sv": "hardware/src/vlsu/vldu.sv",
    "verification/probes/mask_bundle_candidate/vstu.sv": "hardware/src/vlsu/vstu.sv",
    "verification/probes/gather_candidate/masku.sv": "hardware/src/masku/masku.sv",
}
CONFIG_KEYS = ("nr_lanes", "vlen", "qbs", "akv_v2", "verify_axi_delay", "sim_l2_mb")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def normalized_files(manifest: dict, *, overlay: bool) -> tuple[dict[str, str], list[str]]:
    root = Path(manifest["repo_root"])
    result: dict[str, str] = {}
    errors: list[str] = []
    for item in manifest["files"]:
        path = Path(item["path"])
        if path.suffix not in HDL_SUFFIXES:
            continue
        try:
            key = path.relative_to(root).as_posix()
        except ValueError:
            key = str(path)
        if overlay and key in REPLACEMENTS.values():
            continue
        if overlay:
            key = REPLACEMENTS.get(key, key)
        if key in result:
            errors.append(f"duplicate effective HDL input: {key}")
        result[key] = item["sha256"]
        if not path.is_file() or digest(path) != item["sha256"]:
            errors.append(f"source no longer matches manifest: {path}")
    return result, errors


def config(path: Path) -> dict[str, str]:
    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            entries[key] = value
    return {key: entries.get(key, "<missing>") for key in CONFIG_KEYS}


def audit(old_manifest: Path, new_manifest: Path, old_config: Path, new_config: Path) -> dict:
    old = json.loads(old_manifest.read_text(encoding="utf-8"))
    new = json.loads(new_manifest.read_text(encoding="utf-8"))
    old_files, errors = normalized_files(old, overlay=True)
    new_files, new_errors = normalized_files(new, overlay=False)
    errors.extend(new_errors)
    old_keys, new_keys = set(old_files), set(new_files)
    missing = sorted(old_keys - new_keys)
    added = sorted(new_keys - old_keys)
    changed = sorted(key for key in old_keys & new_keys if old_files[key] != new_files[key])
    old_settings, new_settings = config(old_config), config(new_config)
    config_changed = {key: [old_settings[key], new_settings[key]]
                      for key in CONFIG_KEYS if old_settings[key] != new_settings[key]}
    if set(REPLACEMENTS.values()) - old_keys:
        errors.append("overlay replacement is absent from effective HDL inputs")
    return {
        "status": "PASS" if not (errors or missing or added or changed or config_changed) else "FAIL",
        "hdl_file_count": len(old_files),
        "overlay_replacements": REPLACEMENTS,
        "missing": missing,
        "added": added,
        "changed": changed,
        "config_changed": config_changed,
        "errors": errors,
        "old_manifest_sha256": digest(old_manifest),
        "new_manifest_sha256": digest(new_manifest),
        "old_config_sha256": digest(old_config),
        "new_config_sha256": digest(new_config),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay-manifest", type=Path, required=True)
    parser.add_argument("--integrated-manifest", type=Path, required=True)
    parser.add_argument("--overlay-config", type=Path, required=True)
    parser.add_argument("--integrated-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.overlay_manifest, args.integrated_manifest,
                   args.overlay_config, args.integrated_config)
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"{result['status']}: {args.output}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
