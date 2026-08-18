#!/usr/bin/env python3
"""Extract selected FSDB signals into clock-aligned cycle and event CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


VALID_FORMATS = {"b", "o", "d", "u", "h"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sample selected FSDB signals on a clock edge. The output directory "
            "contains cycles.csv, events.csv, metadata.json, and the raw "
            "fsdbreport CSV."
        )
    )
    parser.add_argument("--fsdb", required=True, type=Path, help="input FSDB file")
    parser.add_argument("--profile", required=True, type=Path, help="JSON signal profile")
    parser.add_argument("--output", required=True, type=Path, help="new output directory")
    parser.add_argument("--begin", help="begin time accepted by fsdbreport, e.g. 120us")
    parser.add_argument("--end", help="end time accepted by fsdbreport, e.g. 125us")
    parser.add_argument(
        "--full",
        action="store_true",
        help="explicitly permit extraction over the complete FSDB",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="signal group(s), comma-separated; default uses profile default_groups",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="replace profile placeholders such as {lane}",
    )
    parser.add_argument(
        "--add-signal",
        action="append",
        default=[],
        metavar="ALIAS=PATH",
        help="add one required signal without changing the profile",
    )
    parser.add_argument("--clock", help="override the profile sampling clock")
    parser.add_argument(
        "--edge",
        choices=("posedge", "negedge"),
        help="override the profile sampling edge",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        help="retain at most this many sampled cycles after FSDB extraction",
    )
    parser.add_argument("--cycle-base", type=int, default=0, help="first output cycle number")
    parser.add_argument("--no-events", action="store_true", help="do not write events.csv")
    parser.add_argument(
        "--fsdbreport",
        default="fsdbreport",
        help="fsdbreport executable (default: search PATH)",
    )
    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="list profile groups and exit; FSDB is not opened",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: cannot read profile {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"error: profile root must be a JSON object: {path}")
    return value


def parse_substitutions(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"error: --set expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        if not key:
            raise SystemExit("error: empty --set key")
        result[key] = value
    return result


def substitute(value: str, substitutions: dict[str, str]) -> str:
    try:
        return value.format_map(substitutions)
    except KeyError as exc:
        raise SystemExit(f"error: no --set value for placeholder {exc.args[0]!r}") from exc


def entry_groups(entry: dict[str, Any]) -> set[str]:
    groups = entry.get("groups", entry.get("group", []))
    if isinstance(groups, str):
        return {groups}
    if isinstance(groups, list) and all(isinstance(item, str) for item in groups):
        return set(groups)
    raise SystemExit(f"error: invalid group field in signal {entry!r}")


def selected_groups(args: argparse.Namespace, profile: dict[str, Any]) -> set[str]:
    requested = {
        group.strip()
        for item in args.group
        for group in item.split(",")
        if group.strip()
    }
    if requested:
        return requested
    defaults = profile.get("default_groups", [])
    if isinstance(defaults, str):
        return {defaults}
    if isinstance(defaults, list):
        return set(defaults)
    raise SystemExit("error: default_groups must be a string or list")


def collect_signals(
    args: argparse.Namespace,
    profile: dict[str, Any],
    substitutions: dict[str, str],
) -> list[dict[str, Any]]:
    groups = selected_groups(args, profile)
    entries = profile.get("signals", [])
    if not isinstance(entries, list):
        raise SystemExit("error: profile signals must be a list")

    selected: list[dict[str, Any]] = []
    aliases: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise SystemExit(f"error: signal entry must be an object: {raw!r}")
        if groups and not (entry_groups(raw) & groups):
            continue
        try:
            alias = str(raw["alias"])
            path = substitute(str(raw["path"]), substitutions)
        except KeyError as exc:
            raise SystemExit(f"error: signal entry lacks {exc.args[0]}: {raw!r}") from exc
        fmt = str(raw.get("format", "h"))
        if fmt not in VALID_FORMATS:
            raise SystemExit(f"error: invalid format {fmt!r} for {alias}")
        if alias in aliases:
            raise SystemExit(f"error: duplicate signal alias {alias!r}")
        aliases.add(alias)
        selected.append(
            {
                "alias": alias,
                "path": path,
                "format": fmt,
                "required": bool(raw.get("required", False)),
                "groups": sorted(entry_groups(raw)),
            }
        )

    for item in args.add_signal:
        if "=" not in item:
            raise SystemExit(f"error: --add-signal expects ALIAS=PATH, got {item!r}")
        alias, path = item.split("=", 1)
        if not alias or not path:
            raise SystemExit(f"error: invalid --add-signal {item!r}")
        if alias in aliases:
            raise SystemExit(f"error: duplicate signal alias {alias!r}")
        aliases.add(alias)
        selected.append(
            {
                "alias": alias,
                "path": substitute(path, substitutions),
                "format": "h",
                "required": True,
                "groups": ["command_line"],
            }
        )

    if not selected:
        raise SystemExit(f"error: no signals selected for groups {sorted(groups)}")
    return selected


def collect_derived(
    profile: dict[str, Any], signals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    entries = profile.get("derived", [])
    if not isinstance(entries, list):
        raise SystemExit("error: profile derived field must be a list")
    selected_aliases = {signal["alias"] for signal in signals}
    selected: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit(f"error: derived entry must be an object: {entry!r}")
        inputs = entry.get("inputs", [])
        if isinstance(inputs, list) and all(name in selected_aliases for name in inputs):
            selected.append(entry)
    return selected


def value_as_int(value: str, fmt: str) -> int | None:
    normalized = value.strip().lower().replace("_", "")
    if not normalized or any(char in normalized for char in "xz?"):
        return None
    bases = {"b": 2, "o": 8, "d": 10, "u": 10, "h": 16}
    try:
        return int(normalized, bases[fmt])
    except ValueError:
        return None


def derived_value(
    item: dict[str, Any], row: dict[str, str], formats: dict[str, str]
) -> str:
    op = item.get("op")
    inputs = item.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(name, str) for name in inputs):
        raise SystemExit(f"error: invalid derived inputs: {item!r}")
    values = [value_as_int(row.get(name, "x"), formats.get(name, "b")) for name in inputs]
    if any(value is None for value in values):
        return "x"
    integers = [int(value) for value in values if value is not None]
    if op == "and":
        return "1" if all(integers) else "0"
    if op == "or":
        return "1" if any(integers) else "0"
    if op == "xor":
        result = 0
        for value in integers:
            result ^= bool(value)
        return "1" if result else "0"
    if op == "not" and len(integers) == 1:
        return "0" if integers[0] else "1"
    if op == "eq" and len(integers) == 2:
        return "1" if integers[0] == integers[1] else "0"
    raise SystemExit(f"error: unsupported derived operation: {item!r}")


def prepare_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise SystemExit(f"error: output exists and is not a directory: {path}")
        if any(path.iterdir()):
            raise SystemExit(f"error: output directory is not empty: {path}")
    else:
        path.mkdir(parents=True)


def run_fsdbreport(
    executable: str,
    fsdb: Path,
    raw_csv: Path,
    clock: str,
    edge: str,
    begin: str | None,
    end: str | None,
    signals: list[dict[str, Any]],
    stdout_path: Path,
) -> list[str]:
    command = [executable, str(fsdb)]
    if begin:
        command.extend(["-bt", begin])
    if end:
        command.extend(["-et", end])
    command.extend(["-strobe", f"{clock}=={'1' if edge == 'posedge' else '0'}", "-s"])
    for signal in signals:
        command.extend(
            [signal["path"], "-a", signal["alias"], "-of", signal["format"]]
        )
    command.extend(["-csv", "-o", str(raw_csv), "-nolog"])

    with stdout_path.open("w", encoding="utf-8") as stdout:
        completed = subprocess.run(command, stdout=stdout, stderr=subprocess.STDOUT, check=False)
    if completed.returncode != 0:
        raise SystemExit(
            f"error: fsdbreport exited with {completed.returncode}; see {stdout_path}"
        )
    if not raw_csv.exists() or raw_csv.stat().st_size == 0:
        raise SystemExit(f"error: fsdbreport produced no data; see {stdout_path}")
    return command


def transform_csv(
    raw_csv: Path,
    cycles_csv: Path,
    events_csv: Path | None,
    signals: list[dict[str, Any]],
    derived: list[dict[str, Any]],
    raw_time_unit: str,
    cycle_base: int,
    max_cycles: int | None,
) -> tuple[int, list[str], list[str]]:
    requested_aliases = [item["alias"] for item in signals]
    formats = {item["alias"]: item["format"] for item in signals}
    derived_aliases: list[str] = []
    for item in derived:
        alias = item.get("alias")
        if not isinstance(alias, str) or not alias:
            raise SystemExit(f"error: invalid derived alias: {item!r}")
        if alias in formats or alias in derived_aliases:
            raise SystemExit(f"error: duplicate derived alias {alias!r}")
        derived_aliases.append(alias)
        formats[alias] = "b"

    event_handle = events_csv.open("w", newline="", encoding="utf-8") if events_csv else None
    try:
        with raw_csv.open(newline="", encoding="utf-8") as source, cycles_csv.open(
            "w", newline="", encoding="utf-8"
        ) as destination:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise SystemExit(f"error: missing CSV header in {raw_csv}")
            time_field = reader.fieldnames[0]
            available = set(reader.fieldnames[1:])
            present_aliases = [alias for alias in requested_aliases if alias in available]
            missing_aliases = [alias for alias in requested_aliases if alias not in available]
            output_fields = ["cycle", f"time_{raw_time_unit}", *present_aliases, *derived_aliases]
            writer = csv.DictWriter(destination, fieldnames=output_fields, extrasaction="ignore")
            writer.writeheader()

            event_writer = None
            if event_handle:
                event_writer = csv.DictWriter(
                    event_handle,
                    fieldnames=["cycle", f"time_{raw_time_unit}", "signal", "value", "previous"],
                )
                event_writer.writeheader()

            previous: dict[str, str] = {}
            count = 0
            for raw_row in reader:
                if max_cycles is not None and count >= max_cycles:
                    break
                cycle = cycle_base + count
                row = {
                    "cycle": str(cycle),
                    f"time_{raw_time_unit}": raw_row.get(time_field, ""),
                }
                for alias in present_aliases:
                    row[alias] = raw_row.get(alias, "")
                for item in derived:
                    row[item["alias"]] = derived_value(item, row, formats)
                writer.writerow(row)

                if event_writer:
                    for alias in [*present_aliases, *derived_aliases]:
                        value = row[alias]
                        if alias not in previous or previous[alias] != value:
                            event_writer.writerow(
                                {
                                    "cycle": cycle,
                                    f"time_{raw_time_unit}": row[f"time_{raw_time_unit}"],
                                    "signal": alias,
                                    "value": value,
                                    "previous": previous.get(alias, ""),
                                }
                            )
                            previous[alias] = value
                count += 1
    finally:
        if event_handle:
            event_handle.close()
    return count, present_aliases, missing_aliases


def main() -> int:
    args = parse_args()
    profile = load_json(args.profile)
    profile_signals = profile.get("signals", [])
    all_groups = sorted(
        {group for entry in profile_signals for group in entry_groups(entry)}
    )
    if args.list_groups:
        for group in all_groups:
            print(group)
        return 0

    if not args.fsdb.is_file():
        raise SystemExit(f"error: FSDB does not exist: {args.fsdb}")
    if not args.full and (not args.begin or not args.end):
        raise SystemExit("error: specify both --begin and --end, or explicitly use --full")
    if args.max_cycles is not None and args.max_cycles <= 0:
        raise SystemExit("error: --max-cycles must be positive")

    executable = shutil.which(args.fsdbreport) if "/" not in args.fsdbreport else args.fsdbreport
    if not executable or not Path(executable).is_file():
        raise SystemExit(f"error: fsdbreport executable not found: {args.fsdbreport}")

    substitutions = dict(profile.get("parameters", {}))
    substitutions.update(parse_substitutions(args.set))
    signals = collect_signals(args, profile, substitutions)
    clock = substitute(str(args.clock or profile.get("clock", "")), substitutions)
    if not clock:
        raise SystemExit("error: profile does not define a sampling clock")
    edge = args.edge or str(profile.get("edge", "posedge"))
    if edge not in {"posedge", "negedge"}:
        raise SystemExit(f"error: invalid profile edge {edge!r}")
    raw_time_unit = str(profile.get("raw_time_unit", "raw"))
    derived = collect_derived(profile, signals)

    prepare_output(args.output)
    raw_csv = args.output / "fsdbreport.raw.csv"
    stdout_path = args.output / "fsdbreport.log"
    cycles_csv = args.output / "cycles.csv"
    events_csv = None if args.no_events else args.output / "events.csv"

    command = run_fsdbreport(
        executable,
        args.fsdb.resolve(),
        raw_csv.resolve(),
        clock,
        edge,
        args.begin,
        args.end,
        signals,
        stdout_path.resolve(),
    )
    cycle_count, present, missing = transform_csv(
        raw_csv,
        cycles_csv,
        events_csv,
        signals,
        derived,
        raw_time_unit,
        args.cycle_base,
        args.max_cycles,
    )
    required_missing = [
        signal["alias"] for signal in signals if signal["required"] and signal["alias"] in missing
    ]
    metadata = {
        "profile": str(args.profile.resolve()),
        "profile_name": profile.get("name", args.profile.stem),
        "fsdb": str(args.fsdb.resolve()),
        "clock": clock,
        "edge": edge,
        "begin": args.begin,
        "end": args.end,
        "cycle_base": args.cycle_base,
        "cycle_count": cycle_count,
        "raw_time_unit": raw_time_unit,
        "groups": sorted(selected_groups(args, profile)),
        "present_signals": present,
        "missing_signals": missing,
        "required_missing_signals": required_missing,
        "derived_signals": [item.get("alias") for item in derived],
        "fsdbreport_command": command,
    }
    with (args.output / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=True)
        handle.write("\n")

    print(f"wrote {cycles_csv} ({cycle_count} cycles, {len(present)} signals)")
    if events_csv:
        print(f"wrote {events_csv}")
    if missing:
        print(f"warning: FSDB lacks {len(missing)} selected signals: {', '.join(missing)}")
    if required_missing:
        print(
            f"error: required signals are absent: {', '.join(required_missing)}; "
            f"see {args.output / 'metadata.json'}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
