from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence


_LABEL_RE = re.compile(r"^[.$a-zA-Z_][.$a-zA-Z0-9_]*:\s*")
_SECTION_RE = re.compile(r"^\.section\s+(?P<section>[^,;\s]+)")
_VSET_RE = re.compile(
    r"\b(?:vsetvli|vsetivli)\b.*?\b(e(?:8|16|32|64))\s*,\s*"
    r"(mf8|mf4|mf2|m1|m2|m4|m8)\s*,\s*(ta|tu)\s*,\s*(ma|mu)"
)
_MASK_LOGICAL = {
    "vmand.mm", "vmnand.mm", "vmandn.mm", "vmor.mm",
    "vmnor.mm", "vmorn.mm", "vmxor.mm", "vmxnor.mm",
}


def _generated_instructions(source: Path) -> Iterable[tuple[str, str]]:
    in_generated_code = False
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        section_match = _SECTION_RE.match(line)
        if section_match is not None:
            if section_match.group("section") != ".text":
                in_generated_code = False
            continue
        label_match = _LABEL_RE.match(line)
        if label_match is not None:
            label = label_match.group(0).split(":", 1)[0]
            if label == "main" or re.fullmatch(r"sub_[0-9]+", label):
                in_generated_code = True
            elif label == "test_done":
                in_generated_code = False
            line = line[label_match.end():].strip()
        if not in_generated_code or not line:
            continue
        yield line.split(None, 1)[0].lower(), line


def _family(mnemonic: str) -> str:
    if mnemonic.startswith("vset"):
        return "configuration"
    if _memory_mode(mnemonic) is not None:
        return "load_store"
    if mnemonic in _MASK_LOGICAL:
        return "mask_logical"
    if mnemonic.startswith(("vwred", "vfwred", "vred", "vfred")):
        return "reduction"
    if mnemonic.startswith(("vn", "vfn")):
        return "narrowing"
    if mnemonic.startswith(("vw", "vfw")):
        return "widening"
    if mnemonic.startswith(("vf", "vmf")):
        return "floating_point"
    if mnemonic.startswith(("vslide", "vrgather", "vcompress", "viota", "vid.")):
        return "permutation"
    if mnemonic.startswith(("vm", "vcpop", "vfirst")):
        return "mask_other"
    if mnemonic.startswith(("vaadd", "vaaddu", "vasub", "vasubu", "vsmul", "vss")):
        return "fixed_point"
    return "integer_arithmetic"


def _memory_mode(mnemonic: str) -> str | None:
    if mnemonic.startswith("vset"):
        return None
    if re.match(r"v(?:l[1248]re\d*|s[1248]r)\.v$", mnemonic):
        return "whole_register"
    if mnemonic in {"vlm.v", "vsm.v"}:
        return "mask"
    if any(token in mnemonic for token in ("luxei", "loxei", "suxei", "soxei")):
        return "indexed"
    if mnemonic.startswith(("vlse", "vsse", "vlsseg", "vssseg")):
        return "strided"
    if "seg" in mnemonic and mnemonic.startswith(("vl", "vs")):
        return "segment"
    if mnemonic.startswith(("vle", "vse")):
        return "fault_first" if "ff" in mnemonic else "unit_stride"
    return None


def analyze_stimulus(source: Path) -> dict[str, object]:
    mnemonics: Counter[str] = Counter()
    families: Counter[str] = Counter()
    memory_modes: Counter[str] = Counter()
    sew: Counter[str] = Counter()
    lmul: Counter[str] = Counter()
    tail_policy: Counter[str] = Counter()
    mask_policy: Counter[str] = Counter()
    vector_instruction_count = 0
    masked_instruction_count = 0
    configuration_instruction_count = 0

    for mnemonic, line in _generated_instructions(source):
        if not mnemonic.startswith("v"):
            continue
        vector_instruction_count += 1
        mnemonics[mnemonic] += 1
        families[_family(mnemonic)] += 1
        mode = _memory_mode(mnemonic)
        if mode is not None:
            memory_modes[mode] += 1
        if re.search(r"\bv0\.t\b", line):
            masked_instruction_count += 1
        match = _VSET_RE.search(line)
        if match is not None:
            configuration_instruction_count += 1
            sew[match.group(1)] += 1
            lmul[match.group(2)] += 1
            tail_policy[match.group(3)] += 1
            mask_policy[match.group(4)] += 1

    return {
        "source": str(source),
        "vector_instruction_count": vector_instruction_count,
        "configuration_instruction_count": configuration_instruction_count,
        "masked_instruction_count": masked_instruction_count,
        "mnemonics": dict(sorted(mnemonics.items())),
        "families": dict(sorted(families.items())),
        "memory_modes": dict(sorted(memory_modes.items())),
        "sew": dict(sorted(sew.items())),
        "lmul": dict(sorted(lmul.items())),
        "tail_policy": dict(sorted(tail_policy.items())),
        "mask_policy": dict(sorted(mask_policy.items())),
    }


def write_stimulus_coverage(output: Path, test: str) -> Path:
    sources = sorted((output / "asm_test").glob(f"{test}_*.S"))
    records = [analyze_stimulus(source) for source in sources]
    aggregate: dict[str, Counter[str]] = {
        name: Counter()
        for name in (
            "mnemonics", "families", "memory_modes", "sew", "lmul",
            "tail_policy", "mask_policy",
        )
    }
    for record in records:
        for name, counter in aggregate.items():
            counter.update(record[name])
    report = {
        "test": test,
        "source_count": len(records),
        "vector_instruction_count": sum(
            int(record["vector_instruction_count"]) for record in records
        ),
        "configuration_instruction_count": sum(
            int(record["configuration_instruction_count"]) for record in records
        ),
        "masked_instruction_count": sum(
            int(record["masked_instruction_count"]) for record in records
        ),
        "aggregate": {
            name: dict(sorted(counter.items())) for name, counter in aggregate.items()
        },
        "sources": records,
    }
    path = output / "stimulus_coverage.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def merge_stimulus_coverage(paths: Sequence[Path]) -> dict[str, object]:
    """Merge disjoint profile reports into one campaign-level coverage report."""
    aggregate: dict[str, Counter[str]] = {
        name: Counter()
        for name in (
            "mnemonics", "families", "memory_modes", "sew", "lmul",
            "tail_policy", "mask_policy",
        )
    }
    totals = Counter()
    profiles: list[dict[str, object]] = []
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError(f"expected a JSON object in {path}")
        profile_aggregate = report.get("aggregate")
        if not isinstance(profile_aggregate, dict):
            raise ValueError(f"coverage report has no aggregate object: {path}")
        for name, counter in aggregate.items():
            values = profile_aggregate.get(name, {})
            if not isinstance(values, dict):
                raise ValueError(f"coverage report {path} has invalid {name}")
            counter.update({str(key): int(value) for key, value in values.items()})
        for name in (
            "source_count", "vector_instruction_count",
            "configuration_instruction_count", "masked_instruction_count",
        ):
            totals[name] += int(report.get(name, 0))
        profiles.append({
            "test": str(report.get("test", path.parent.name)),
            "source_count": int(report.get("source_count", 0)),
            "vector_instruction_count": int(report.get("vector_instruction_count", 0)),
            "path": str(path),
        })

    return {
        **dict(totals),
        "profile_count": len(profiles),
        "profiles": profiles,
        "aggregate": {
            name: dict(sorted(counter.items())) for name, counter in aggregate.items()
        },
    }
