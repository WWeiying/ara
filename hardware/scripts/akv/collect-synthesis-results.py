#!/usr/bin/env python3

"""Collect fresh standalone or integrated QBS/AKV DC evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CORNER = {
    "technology": "TSMC28",
    "clock_period_ns": 1.0,
    "setup_uncertainty_ns": 0.15,
}


class CollectionError(ValueError):
    """Synthesis evidence is absent, stale, malformed, or inconsistent."""


@dataclass(frozen=True)
class CollectionSpec:
    mode: str
    root: Path
    filelist: Path
    input_sdc: Path
    summary_rpt: Path
    area_rpt: Path
    generated_artifacts: tuple[Path, ...]
    source_inputs: tuple[Path, ...]
    output: Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve()))
    except ValueError:
        return str(resolved)


def resolve_recorded(raw: str, root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def artifact(path: Path, root: Path) -> dict[str, int | str]:
    if not path.is_file():
        raise CollectionError(f"missing artifact: {path}")
    stat = path.stat()
    return {
        "path": relative(path, root),
        "sha256": sha256(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def read_key_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise CollectionError(f"missing physical summary: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            raise CollectionError(f"malformed summary line: {line}")
        key, value = line.split("=", 1)
        if key in values:
            raise CollectionError(f"duplicate summary field: {key}")
        values[key] = value
    return values


def required_float(values: dict[str, str], key: str) -> float:
    try:
        value = float(values[key])
    except (KeyError, ValueError) as error:
        raise CollectionError(f"invalid or missing numeric field: {key}") from error
    if not math.isfinite(value):
        raise CollectionError(f"non-finite numeric field: {key}")
    return value


def required_int(values: dict[str, str], key: str) -> int:
    try:
        return int(values[key])
    except (KeyError, ValueError) as error:
        raise CollectionError(f"invalid or missing integer field: {key}") from error


def parse_area_report(path: Path) -> tuple[float, float]:
    text = path.read_text(encoding="utf-8", errors="replace")

    def one(label: str) -> float:
        match = re.search(rf"(?m)^\s*{re.escape(label)}:\s+([0-9]+(?:\.[0-9]+)?)\s*$", text)
        if not match:
            raise CollectionError(f"area report is missing {label}")
        return float(match.group(1))

    return one("Total cell area"), one("Macro/Black Box area")


def filelist_inputs(filelist: Path) -> list[Path]:
    if not filelist.is_file():
        raise CollectionError(f"missing DC filelist: {filelist}")
    sources: set[Path] = set()
    include_dirs: set[Path] = set()
    for raw in filelist.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("+incdir+"):
            include_dirs.add(Path(line.removeprefix("+incdir+")))
        elif line.endswith((".sv", ".v")):
            sources.add(Path(line))
    for directory in include_dirs:
        if not directory.is_dir():
            raise CollectionError(f"filelist include directory is missing: {directory}")
        for suffix in ("*.svh", "*.vh"):
            sources.update(path for path in directory.rglob(suffix) if path.is_file())
    missing = sorted(str(path) for path in sources if not path.is_file())
    if missing:
        raise CollectionError("filelist source inputs are missing: " + ", ".join(missing[:5]))
    return sorted(sources, key=lambda path: str(path.resolve()))


def source_digest(filelist: Path, source_inputs: tuple[Path, ...], root: Path) -> str:
    paths = [filelist, *filelist_inputs(filelist), *source_inputs]
    unique = {path.resolve(): path for path in paths}
    digest = hashlib.sha256()
    for resolved in sorted(unique):
        path = unique[resolved]
        if not path.is_file():
            raise CollectionError(f"source input is missing: {path}")
        digest.update(relative(path, root).encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def library_inputs(source_inputs: tuple[Path, ...]) -> list[Path]:
    libraries: set[Path] = set()
    pattern = re.compile(r"(/[A-Za-z0-9_./+:-]+\.(?:db|sldb))(?=\s|\"|$)")
    for source in source_inputs:
        text = source.read_text(encoding="utf-8", errors="replace")
        active = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        libraries.update(Path(match) for match in pattern.findall(active))
    missing = sorted(str(path) for path in libraries if not path.is_file())
    if missing:
        raise CollectionError("physical libraries are missing: " + ", ".join(missing[:5]))
    names = [path.name.lower() for path in libraries]
    if not any("tcbn28hpcplus" in name for name in names):
        raise CollectionError("TSMC28 standard-cell DB was not identified")
    if not any("64x256" in name for name in names):
        raise CollectionError("AKV 64x256 SRAM DB was not identified")
    return sorted(libraries, key=lambda path: str(path.resolve()))


def validate_metrics(mode: str, values: dict[str, str], area_rpt: Path) -> dict[str, int | float | str]:
    expected_scope = {
        "standalone": "akv_engine_standalone",
        "integrated": "ara_soc_integrated",
    }[mode]
    if values.get("scope") != expected_scope:
        raise CollectionError(f"wrong synthesis scope: {values.get('scope')}")

    clock = required_float(values, "clock_period_ns")
    uncertainty = required_float(values, "clock_uncertainty_ns")
    if clock != CORNER["clock_period_ns"] or uncertainty != CORNER["setup_uncertainty_ns"]:
        raise CollectionError(f"wrong physical corner: clock={clock}, uncertainty={uncertainty}")

    macro_count = required_int(values, "akv_sram_macro_count")
    v1_count = required_int(values, "akv_v1_sram_macro_count")
    v2_count = required_int(values, "akv_v2_sram_macro_count")
    capacity = required_int(values, "physical_sram_capacity_bits")
    if (macro_count, v1_count, v2_count) != (20, 4, 16):
        raise CollectionError(
            f"wrong AKV SRAM organization: total={macro_count}, v1={v1_count}, v2={v2_count}"
        )
    if capacity != macro_count * 64 * 256:
        raise CollectionError(f"wrong AKV SRAM physical capacity: {capacity}")

    report_total, report_macro = parse_area_report(area_rpt)
    summary_total = required_float(values, "design_total_area_um2")
    tolerance = max(0.01, report_total * 1e-6)
    if abs(summary_total - report_total) > tolerance:
        raise CollectionError(
            f"summary/report total area mismatch: {summary_total} versus {report_total}"
        )

    if mode == "standalone":
        macro_area = required_float(values, "design_macro_area_um2")
        logic_area = required_float(values, "design_logic_area_um2")
        if abs(macro_area - report_macro) > max(0.01, report_macro * 1e-6):
            raise CollectionError("standalone macro area differs from report_area")
    else:
        macro_area = report_macro
        logic_area = report_total - report_macro
    if min(report_total, macro_area, logic_area) <= 0:
        raise CollectionError("synthesis area must be positive")
    if abs(report_total - macro_area - logic_area) > tolerance:
        raise CollectionError("logic and macro area do not sum to total cell area")

    return {
        "scope": expected_scope,
        "clock_period_ns": clock,
        "setup_uncertainty_ns": uncertainty,
        "akv_sram_macro_count": macro_count,
        "akv_v1_sram_macro_count": v1_count,
        "akv_v2_sram_macro_count": v2_count,
        "akv_sram_capacity_bits": capacity,
        "design_total_area_um2": report_total,
        "design_macro_area_um2": macro_area,
        "design_logic_area_um2": logic_area,
        "worst_setup_slack_ns": required_float(values, "worst_setup_slack_ns"),
        "worst_reg_to_reg_setup_slack_ns": required_float(
            values, "worst_reg_to_reg_setup_slack_ns"
        ),
    }


def default_spec(mode: str, root: Path = ROOT) -> CollectionSpec:
    filelist = root / "backend/flist/ara_soc_dc.f"
    if mode == "standalone":
        base = root / "verification/akv/synthesis/akv_engine_dc_out"
        source_inputs = (
            root / "verification/akv/synthesis/akv_engine_synth_wrapper.sv",
            root / "verification/akv/synthesis/akv_engine_dc.tcl",
            root / "verification/akv/synthesis/akv_engine.sdc",
        )
        return CollectionSpec(
            mode=mode,
            root=root,
            filelist=filelist,
            input_sdc=source_inputs[2],
            summary_rpt=base / "engine_summary.rpt",
            area_rpt=base / "area.rpt",
            generated_artifacts=(
                base / "engine_summary.rpt",
                base / "area.rpt",
                base / "timing.rpt",
                base / "timing_reg_to_reg.rpt",
                base / "qor.rpt",
                base / "akv_engine.ddc",
                base / "akv_engine.v",
                base / "akv_engine.sdc",
                root / "verification/akv/synthesis/akv_engine_dc.log",
            ),
            source_inputs=source_inputs,
            output=base / "synthesis_summary.json",
        )
    if mode == "integrated":
        base = root / "backend/syn/ara_soc/v1-dc"
        reports = base / "reports"
        source_inputs = (
            root / "backend/syn/ara_soc/v1-dc/global_scripts/dc.tcl",
            root / "backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env",
            root / "backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.gui",
            root / "backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.main",
            root / "backend/syn/ara_soc/v1-dc/global_scripts/dc_dont_use.tcl",
            root / "backend/syn/ara_soc/v1-dc/local_scripts/ara_soc.sdc",
            root / "backend/syn/ara_soc/v1-dc/run/.synopsys_dc.setup",
            root / "backend/syn/ara_soc/v1-dc/run/run.cmd",
        )
        return CollectionSpec(
            mode=mode,
            root=root,
            filelist=filelist,
            input_sdc=source_inputs[5],
            summary_rpt=reports / "physical_summary.rpt",
            area_rpt=reports / "area.rpt",
            generated_artifacts=(
                reports / "physical_summary.rpt",
                reports / "area.rpt",
                reports / "clk_i_max.tim",
                reports / "qor.rpt",
                base / "outputs/ara_soc_dc.ddc",
                base / "outputs/ara_soc_dc.v",
                base / "outputs/ara_soc_dc.sdc",
                base / "run/dc.log",
            ),
            source_inputs=source_inputs,
            output=reports / "synthesis_summary.json",
        )
    raise CollectionError(f"unsupported synthesis mode: {mode}")


def collect(spec: CollectionSpec) -> dict[str, object]:
    if not spec.filelist.is_file():
        raise CollectionError(f"missing DC filelist: {spec.filelist}")
    libraries = library_inputs(spec.source_inputs)
    synthesis_inputs = [
        spec.filelist,
        *filelist_inputs(spec.filelist),
        *spec.source_inputs,
        *libraries,
    ]
    newest_input_mtime = max(path.stat().st_mtime_ns for path in synthesis_inputs)
    generated = [artifact(path, spec.root) for path in spec.generated_artifacts]
    stale = [
        item["path"]
        for item in generated
        if int(item["mtime_ns"]) < newest_input_mtime
    ]
    if stale:
        raise CollectionError(
            "synthesis artifacts predate current synthesis inputs: "
            + ", ".join(str(path) for path in stale)
        )

    values = read_key_values(spec.summary_rpt)
    metrics = validate_metrics(spec.mode, values, spec.area_rpt)
    summary = {
        "schema_version": 1,
        "status": "PASS",
        "mode": spec.mode,
        "corner": CORNER,
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=spec.root, text=True
        ).strip(),
        "filelist": artifact(spec.filelist, spec.root),
        "input_sdc": artifact(spec.input_sdc, spec.root),
        "source_inputs": [relative(path, spec.root) for path in spec.source_inputs],
        "source_digest": source_digest(spec.filelist, spec.source_inputs, spec.root),
        "library_artifacts": [artifact(path, spec.root) for path in libraries],
        "metrics": metrics,
        "artifacts": generated,
    }
    spec.output.parent.mkdir(parents=True, exist_ok=True)
    spec.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def validate_summary(path: Path, expected_mode: str, root: Path = ROOT) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    summary = json.loads(path.read_text(encoding="utf-8"))
    if (
        summary.get("schema_version") != 1
        or summary.get("status") != "PASS"
        or summary.get("mode") != expected_mode
        or summary.get("corner") != CORNER
    ):
        raise CollectionError("synthesis summary header or corner is invalid")

    recorded_filelist = summary.get("filelist", {})
    filelist = resolve_recorded(str(recorded_filelist.get("path", "")), root)
    if not filelist.is_file() or sha256(filelist) != recorded_filelist.get("sha256"):
        raise CollectionError("current DC filelist differs from synthesized filelist")

    for item in [
        summary.get("input_sdc", {}),
        *summary.get("library_artifacts", []),
        *summary.get("artifacts", []),
    ]:
        artifact_path = resolve_recorded(str(item.get("path", "")), root)
        if not artifact_path.is_file() or sha256(artifact_path) != item.get("sha256"):
            raise CollectionError(f"synthesis artifact changed: {item.get('path')}")

    source_inputs = tuple(resolve_recorded(raw, root) for raw in summary.get("source_inputs", []))
    observed_libraries = library_inputs(source_inputs)
    recorded_libraries = {
        resolve_recorded(str(item.get("path", "")), root).resolve()
        for item in summary.get("library_artifacts", [])
    }
    if {path.resolve() for path in observed_libraries} != recorded_libraries:
        raise CollectionError("current physical library set differs from synthesis")
    observed_digest = source_digest(filelist, source_inputs, root)
    if observed_digest != summary.get("source_digest"):
        raise CollectionError("current RTL or synthesis inputs differ from synthesized sources")

    metrics = summary.get("metrics", {})
    if (
        metrics.get("akv_sram_macro_count") != 20
        or metrics.get("akv_v1_sram_macro_count") != 4
        or metrics.get("akv_v2_sram_macro_count") != 16
        or float(metrics.get("design_total_area_um2", 0)) <= 0
        or float(metrics.get("design_logic_area_um2", 0)) <= 0
    ):
        raise CollectionError("synthesis summary metrics violate the AKV physical contract")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("standalone", "integrated"), required=True)
    args = parser.parse_args(argv)
    try:
        summary = collect(default_spec(args.mode))
    except (CollectionError, OSError, subprocess.CalledProcessError) as error:
        print(f"SYNTHESIS COLLECTION FAIL: {error}", file=sys.stderr)
        return 1
    metrics = summary["metrics"]
    print(
        "SYNTHESIS COLLECTION PASS: "
        f"mode={args.mode} area={metrics['design_total_area_um2']:.3f} um^2 "
        f"reg2reg_slack={metrics['worst_reg_to_reg_setup_slack_ns']:.3f} ns "
        f"AKV_macros={metrics['akv_sram_macro_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
