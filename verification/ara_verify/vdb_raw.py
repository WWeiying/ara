"""Export raw VCS VDB test records without interpreting coverage scores.

Usage: PYTHONPATH=verification python3 -m ara_verify.vdb_raw \
    --compile-vdb simv.vdb --test-vdb code.vdb \
    --instance-prefix ara_tb.dut > raw.jsonl
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TextIO


METRICS = ("line", "cond", "fsm", "tgl", "branch")
RECORD_TAGS = ("instance_data", "instance_intervaldata")


def _open_xml(path: Path):
    with path.open("rb") as stream:
        compressed = stream.read(2) == b"\x1f\x8b"
    return gzip.open(path, "rb") if compressed else path.open("rb")


def _xml_version(path: Path, root_tag: str) -> str:
    with _open_xml(path) as stream:
        parser = ET.iterparse(stream, events=("start",))
        _, root = next(parser)
        if root.tag != root_tag:
            raise ValueError(f"{path}: expected {root_tag}, found {root.tag}")
        for _, element in parser:
            if element.tag == "ucapi_version":
                version = element.get("patch_str")
                if version:
                    return version
                break
    raise ValueError(f"{path}: missing ucapi_version patch_str")


def _test_directory(test_vdb: Path, test_name: str | None) -> tuple[str, Path]:
    root = test_vdb / "snps/coverage/db/testdata"
    if test_name:
        selected = root / test_name
        if not selected.is_dir():
            raise ValueError(f"test not found: {selected}")
        return test_name, selected
    names = sorted(path.name for path in root.iterdir() if path.is_dir())
    if len(names) != 1:
        raise ValueError(f"{root}: expected one test directory, found {names}; use --test-name")
    return names[0], root / names[0]


def _matches(instance: str, prefix: str | None) -> bool:
    return prefix is None or instance == prefix or instance.startswith(prefix + ".")


def _emit(out: TextIO, record: dict[str, object]) -> None:
    out.write(json.dumps(record, sort_keys=True) + "\n")


def export_raw(
    compile_vdb: Path,
    test_vdb: Path,
    metrics: tuple[str, ...],
    instance_prefix: str | None,
    test_name: str | None,
    out: TextIO,
    summary_only: bool = False,
) -> dict[str, object]:
    compile_vdb = compile_vdb.resolve()
    test_vdb = test_vdb.resolve()
    version_path = compile_vdb / ".vdb_version"
    version = version_path.read_text(encoding="ascii").strip()
    design = compile_vdb / "snps/coverage/db/design/verilog.design.xml"
    if _xml_version(design, "design") != version:
        raise ValueError(f"{design}: version differs from {version_path}")
    selected_name, test_dir = _test_directory(test_vdb, test_name)
    paths = {metric: test_dir / f"{metric}.verilog.data.xml" for metric in metrics}
    for path in paths.values():
        if not path.is_file():
            raise ValueError(f"missing metric data: {path}")

    metadata: dict[str, object] = {
        "type": "metadata",
        "format": "vcs-vdb-raw-v1",
        "compile_vdb": str(compile_vdb),
        "test_vdb": str(test_vdb),
        "test_name": selected_name,
        "vcs_version": version,
        "instance_prefix": instance_prefix,
        "metrics": list(metrics),
        "coverage_scores_computed": False,
    }
    if not summary_only:
        _emit(out, metadata)

    shape_dir = compile_vdb / "snps/coverage/db/shape"
    summaries: dict[str, dict[str, object]] = {}
    for metric, path in paths.items():
        counts: dict[str, int] = {
            "records": 0,
            "bitmap_records": 0,
            "interval_records": 0,
            "raw_bitmap_characters": 0,
            "raw_one_characters": 0,
        }
        with _open_xml(path) as stream:
            parser = ET.iterparse(stream, events=("start", "end"))
            _, root = next(parser)
            if root.tag != "covdata":
                raise ValueError(f"{path}: expected covdata, found {root.tag}")
            saw_version = False
            for event, element in parser:
                if event != "end" or element is root:
                    continue
                if element.tag == "ucapi_version":
                    if element.get("patch_str") != version:
                        raise ValueError(f"{path}: version differs from {version}")
                    saw_version = True
                elif element.tag in RECORD_TAGS:
                    if not saw_version:
                        raise ValueError(f"{path}: data before ucapi_version")
                    instance = element.get("name")
                    value = element.get("value")
                    if instance is None or value is None:
                        raise ValueError(f"{path}: record missing name or value")
                    if _matches(instance, instance_prefix):
                        counts["records"] += 1
                        kind = element.tag
                        if kind == "instance_data":
                            counts["bitmap_records"] += 1
                            if set(value) <= {"0", "1"}:
                                counts["raw_bitmap_characters"] += len(value)
                                counts["raw_one_characters"] += value.count("1")
                        else:
                            counts["interval_records"] += 1
                        if not summary_only:
                            _emit(out, {
                                "type": "raw_record",
                                "metric": metric,
                                "record_type": kind,
                                "instance": instance,
                                "value": value,
                                "checksum": element.get("chksum"),
                            })
                else:
                    raise ValueError(f"{path}: unsupported XML element {element.tag}")
                root.clear()
            if not saw_version:
                raise ValueError(f"{path}: missing ucapi_version")
        summaries[metric] = {
            **counts,
            "shape_file_present": (shape_dir / f"{metric}.verilog.shape.xml").is_file(),
        }

    summary: dict[str, object] = {
        "type": "summary",
        "vcs_version": version,
        "test_name": selected_name,
        "instance_prefix": instance_prefix,
        "metrics": summaries,
        "coverage_scores_computed": False,
        "note": "Raw bitmap characters and interval records are not URG coverage points or percentages.",
    }
    _emit(out, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile-vdb", type=Path, required=True)
    parser.add_argument("--test-vdb", type=Path, required=True)
    parser.add_argument("--test-name")
    parser.add_argument("--instance-prefix")
    parser.add_argument("--metrics", default=",".join(METRICS))
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args(argv)
    metrics = tuple(part.strip() for part in args.metrics.split(","))
    if not metrics or len(set(metrics)) != len(metrics) or any(metric not in METRICS for metric in metrics):
        parser.error(f"metrics must be unique names from {','.join(METRICS)}")
    try:
        export_raw(args.compile_vdb, args.test_vdb, metrics, args.instance_prefix,
                   args.test_name, sys.stdout, args.summary_only)
    except (OSError, EOFError, ET.ParseError, ValueError) as error:
        print(f"VDB extraction failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
