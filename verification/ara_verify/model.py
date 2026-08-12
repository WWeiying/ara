from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class TestCase:
    name: str
    kind: str
    build_target: str
    binary: Path
    testcase: str
    timeout_s: int


@dataclass(frozen=True)
class CheckResult:
    level: str
    name: str
    detail: str


@dataclass
class TestResult:
    name: str
    kind: str
    status: str
    returncode: Optional[int]
    elapsed_s: float
    reason: str
    artifact_dir: Path
