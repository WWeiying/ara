#!/usr/bin/env python3

"""Reject stale or incomplete QBS/AKV Design Compiler inputs."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FILELIST = ROOT / "backend/flist/ara_soc_dc.f"
DEFAULT_SDC = ROOT / "backend/syn/ara_soc/v1-dc/local_scripts/ara_soc.sdc"
DEFAULT_SETUP = (
    ROOT / "backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env"
)
DEFAULT_AKV_SRAM_DB = Path(
    "/home/wangwy/ara/backend/library/mem/"
    "ts1n28hpcpuhdsvtb64x256m1swbso_170a/DB/"
    "ts1n28hpcpuhdsvtb64x256m1swbso_170a_tt0p9v25c.db"
)

COMMON_SOURCES = (
    "hardware/include/rvv_pkg.sv",
    "hardware/include/ara_pkg.sv",
    "hardware/src/vlsu/vlsu.sv",
    "hardware/src/ara_soc.sv",
)
QBS_SOURCES = (
    "hardware/include/qbs_pkg.sv",
    "hardware/src/vlsu/qbs/qbs_profile_decoder.sv",
    "hardware/src/vlsu/qbs/qbs_dot_array.sv",
    "hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv",
    "hardware/src/vlsu/qbs/qbs_read_engine.sv",
    "hardware/src/vlsu/qbs/qbs_activation_context.sv",
    "hardware/src/vlsu/qbs/qbs_block_adapter.sv",
    "hardware/src/vlsu/qbs/qbs_profile_engine_int.sv",
    "hardware/src/vlsu/qbs/qbs_fp_accumulator.sv",
    "hardware/src/vlsu/qbs/qbs_compute_engine.sv",
    "hardware/src/vlsu/qbs/qbs_commit.sv",
    "hardware/src/vlsu/qbs/qbs_engine.sv",
)
AKV_SOURCES = (
    "hardware/include/akv_pkg.sv",
    "hardware/src/vlsu/akv/akv_context.sv",
    "hardware/src/vlsu/akv/akv_engine.sv",
)
AKV_V2_SOURCES = ("hardware/src/vlsu/akv/akv_v2_context.sv",)
AKV_SRAM_BLACKBOX = (
    "backend/blackbox/"
    "ts1n28hpcpuhdsvtb64x256m1swbso_170a_tt0p9v25c.v"
)


class PreflightError(ValueError):
    """A synthesis input does not satisfy the requested configuration."""


@dataclass(frozen=True)
class Options:
    filelist: Path
    sdc: Path
    setup: Path
    sram_db: Path
    require_qbs: bool = False
    require_akv: bool = False
    require_akv_v2: bool = False
    require_macro_sram: bool = False
    nr_lanes: int | None = None
    vlen: int | None = None


def _read(path: Path, label: str) -> str:
    if not path.is_file():
        raise PreflightError(f"missing {label}: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def _filelist_entries(text: str) -> tuple[set[str], list[Path]]:
    defines: set[str] = set()
    sources: list[Path] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("//", "#")):
            continue
        if line.startswith("+define+"):
            defines.add(line.removeprefix("+define+"))
        elif line.endswith((".sv", ".v")):
            sources.append(Path(line))
    return defines, sources


def _has_source(sources: list[Path], expected: str) -> bool:
    expected_path = Path(expected).as_posix()
    return any(source.as_posix().endswith(expected_path) for source in sources)


def _require_sources(sources: list[Path], expected: tuple[str, ...]) -> None:
    missing = [source for source in expected if not _has_source(sources, source)]
    if missing:
        raise PreflightError("filelist is missing sources: " + ", ".join(missing))


def _require_define(defines: set[str], expected: str) -> None:
    if expected not in defines:
        raise PreflightError(f"filelist is missing +define+{expected}")


def _check_order(sources: list[Path], before: str, after: str) -> None:
    before_index = next(
        (index for index, source in enumerate(sources) if source.as_posix().endswith(before)),
        None,
    )
    after_index = next(
        (index for index, source in enumerate(sources) if source.as_posix().endswith(after)),
        None,
    )
    if before_index is None or after_index is None or before_index >= after_index:
        raise PreflightError(f"compile order must place {before} before {after}")


def _check_sdc(text: str) -> None:
    text = re.sub(r"\\\s*\n\s*", " ", text)
    required_patterns = {
        "1 GHz clock multiplier": r"(?m)^\s*set\s+clk_mul\s+1\.0\s*$",
        "zero additive uncertainty": r"(?m)^\s*set\s+uncertainty_add\s+0\s*$",
        "1 ns clock": (
            r"create_clock\s+-name\s+clk_i\s+-period\s+"
            r"\[expr\s*\{\s*1\s*\*\s*\$clk_mul\s*\}\]"
        ),
        "0.15 ns setup uncertainty": (
            r"set_clock_uncertainty\s+-setup\s+\[expr\s*\{\s*"
            r"\(0\.15\s*\+\s*\$uncertainty_add\)\s*\*\s*\$clk_mul\s*\}\]"
        ),
    }
    missing = [label for label, pattern in required_patterns.items() if not re.search(pattern, text)]
    if missing:
        raise PreflightError("SDC is missing the required " + ", ".join(missing))


def audit(options: Options) -> dict[str, int | str]:
    filelist_text = _read(options.filelist, "DC filelist")
    sdc_text = _read(options.sdc, "SDC")
    setup_text = _read(options.setup, "DC setup")
    defines, sources = _filelist_entries(filelist_text)

    _require_define(defines, "SYNTHESIS")
    _require_define(defines, "TARGET_SYNTHESIS")
    _require_sources(sources, COMMON_SOURCES)
    _check_order(sources, "hardware/include/rvv_pkg.sv", "hardware/src/vlsu/vlsu.sv")
    _check_order(sources, "hardware/include/ara_pkg.sv", "hardware/src/ara_soc.sv")

    missing_files = [
        str(source) for source in sources if source.is_absolute() and not source.is_file()
    ]
    if missing_files:
        raise PreflightError("filelist references missing files: " + ", ".join(missing_files[:5]))

    if options.nr_lanes is not None:
        _require_define(defines, f"NR_LANES={options.nr_lanes}")
    if options.vlen is not None:
        _require_define(defines, f"VLEN={options.vlen}")

    if options.require_qbs:
        _require_define(defines, "ARA_QBS_ENABLE=1")
        _require_sources(sources, QBS_SOURCES)
        _check_order(sources, "hardware/include/qbs_pkg.sv", "hardware/src/vlsu/qbs/qbs_engine.sv")

    if options.require_akv or options.require_akv_v2:
        _require_define(defines, "ARA_AKV_ENABLE=1")
        _require_sources(sources, AKV_SOURCES)
        _check_order(sources, "hardware/include/akv_pkg.sv", "hardware/src/vlsu/akv/akv_engine.sv")

    if options.require_akv_v2:
        _require_define(defines, "ARA_AKV_V2_ENABLE=1")
        _require_sources(sources, AKV_V2_SOURCES)
        _check_order(
            sources,
            "hardware/src/vlsu/akv/akv_v2_context.sv",
            "hardware/src/vlsu/akv/akv_engine.sv",
        )

    if options.require_macro_sram:
        _require_define(defines, "TARGET_SRAM_MC")
        _require_define(defines, "TARGET_SRAM_BLACKBOX")
        _require_define(defines, "TARGET_TECH_CELLS_GENERIC_EXCLUDE_TC_SRAM")
        _require_sources(sources, (AKV_SRAM_BLACKBOX,))
        generic_sram = (
            "hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv",
            "hardware/deps/tech_cells_generic/src/rtl/tc_sram_impl.sv",
        )
        present_generic = [source for source in generic_sram if _has_source(sources, source)]
        if present_generic:
            raise PreflightError(
                "macro-SRAM filelist still contains generic SRAM implementations: "
                + ", ".join(present_generic)
            )
        if not options.sram_db.is_file():
            raise PreflightError(f"missing AKV SRAM DB: {options.sram_db}")
        if str(options.sram_db) not in setup_text:
            raise PreflightError("DC setup does not include the AKV 64x256 SRAM DB")

    _check_sdc(sdc_text)
    return {
        "filelist": str(options.filelist),
        "defines": len(defines),
        "sources": len(sources),
        "clock_period_ns": 1,
        "setup_uncertainty_ns": "0.15",
    }


def parse_args(argv: list[str] | None = None) -> Options:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filelist", type=Path, default=DEFAULT_FILELIST)
    parser.add_argument("--sdc", type=Path, default=DEFAULT_SDC)
    parser.add_argument("--setup", type=Path, default=DEFAULT_SETUP)
    parser.add_argument("--sram-db", type=Path, default=DEFAULT_AKV_SRAM_DB)
    parser.add_argument("--require-qbs", action="store_true")
    parser.add_argument("--require-akv", action="store_true")
    parser.add_argument("--require-akv-v2", action="store_true")
    parser.add_argument("--require-macro-sram", action="store_true")
    parser.add_argument("--nr-lanes", type=int)
    parser.add_argument("--vlen", type=int)
    args = parser.parse_args(argv)
    return Options(**vars(args))


def main(argv: list[str] | None = None) -> int:
    try:
        summary = audit(parse_args(argv))
    except PreflightError as error:
        print(f"SYNTHESIS PREFLIGHT FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "SYNTHESIS PREFLIGHT PASS: "
        f"{summary['sources']} sources, {summary['defines']} defines, "
        f"{summary['clock_period_ns']} ns clock, "
        f"{summary['setup_uncertainty_ns']} ns setup uncertainty"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
