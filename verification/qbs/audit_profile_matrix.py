"""Audit the focused QBS profile-engine test matrix, not full-DUT coverage."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from collections import Counter
from pathlib import Path


CASE = re.compile(
    r"^QBS RTL case (\d+) PASS profile=(\d+) M=(\d+) rows=(\d+) "
    r"pattern=(\d+) first_cycles=(\d+) repeat_cycles=(\d+)$", re.MULTILINE
)
FINAL = re.compile(r"^QBS profile engine PASS: (\d+) cases$", re.MULTILINE)
PROFILES = {
    1: "Q4_K", 2: "Q6_K", 3: "Q4_0", 4: "Q5_K", 5: "Q3_K",
    6: "Q8_0_WEIGHT", 7: "Q2_K", 8: "Q5_0", 9: "IQ4_NL",
}


def expected_matrix() -> set[tuple[int, int, int, int]]:
    return {
        (profile, m, rows, pattern)
        for profile, m, rows in itertools.product(PROFILES, range(1, 5), range(1, 5))
        for pattern in (0, 1, 2, 3) if pattern != 3 or profile == 6
    }


def audit(text: str) -> dict[str, object]:
    matches = list(CASE.finditer(text))
    rows = [tuple(map(int, match.groups())) for match in matches]
    seen = Counter((profile, m, active_rows, pattern)
                   for _, profile, m, active_rows, pattern, _, _ in rows)
    expected = expected_matrix()
    missing = sorted(expected - seen.keys())
    unexpected = sorted(seen.keys() - expected)
    duplicates = sorted(key for key, count in seen.items() if count > 1)
    ids = sorted(row[0] for row in rows)
    finals = [int(value) for value in FINAL.findall(text)]
    issues = []
    if missing:
        issues.append(f"missing {len(missing)} required profile combinations")
    if unexpected:
        issues.append(f"unexpected {len(unexpected)} profile combinations")
    if duplicates:
        issues.append(f"duplicated {len(duplicates)} profile combinations")
    if ids != list(range(len(expected))):
        issues.append("case IDs are not exactly the expected contiguous set")
    if finals != [len(expected)]:
        issues.append("exactly one matching final PASS summary is required")
    if re.search(r"(?:^|\n)(?:Error:|Fatal:|UVM_ERROR|QBS RTL case \d+ FAIL)", text):
        issues.append("error or failing case found in simulator log")
    if any(first <= 0 or repeat <= 0 for *_, first, repeat in rows):
        issues.append("nonpositive first/repeated block latency")
    return {
        "status": "PASS" if not issues else "INCOMPLETE",
        "scope": "QBS profile-engine constructed vectors; not full-DUT or model-data signoff",
        "passed_cases": len(rows),
        "expected_cases": len(expected),
        "profile_counts": {PROFILES[profile]: sum(key[0] == profile for key in seen)
                           for profile in PROFILES},
        "missing": missing,
        "unexpected": unexpected,
        "duplicates": duplicates,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    log = args.log.read_bytes()
    result = audit(log.decode("utf-8", errors="replace"))
    result["log_sha256"] = hashlib.sha256(log).hexdigest()
    result["log"] = str(args.log.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"QBS profile matrix: {result['status']} "
          f"({len(expected_matrix()) - len(result['missing'])}/{len(expected_matrix())} bins)")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
