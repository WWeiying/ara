from __future__ import annotations

import fnmatch
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from .model import TestCase


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Catalog:
    tests: Mapping[str, TestCase]
    suites: Mapping[str, Mapping[str, object]]

    def resolve_suite(self, name: str) -> List[TestCase]:
        if name not in self.suites:
            raise ManifestError(f"unknown suite: {name}")
        spec = self.suites[name]
        selected: "OrderedDict[str, TestCase]" = OrderedDict()

        explicit = spec.get("tests", [])
        if not isinstance(explicit, list):
            raise ManifestError(f"suite {name}: tests must be a list")
        for test_name in explicit:
            if test_name not in self.tests:
                raise ManifestError(f"suite {name}: unknown test {test_name}")
            selected[test_name] = self.tests[test_name]

        includes = spec.get("include", [])
        excludes = spec.get("exclude", [])
        if not isinstance(includes, list) or not isinstance(excludes, list):
            raise ManifestError(f"suite {name}: include/exclude must be lists")
        for pattern in includes:
            for test_name, test in self.tests.items():
                if fnmatch.fnmatchcase(test_name, pattern):
                    selected[test_name] = test
        for pattern in excludes:
            for test_name in list(selected):
                if fnmatch.fnmatchcase(test_name, pattern):
                    del selected[test_name]

        if not selected:
            raise ManifestError(f"suite {name} selects no tests")
        return list(selected.values())

    def select(self, selectors: Sequence[str]) -> List[TestCase]:
        selected: "OrderedDict[str, TestCase]" = OrderedDict()
        for selector in selectors:
            matches = [
                (name, test)
                for name, test in self.tests.items()
                if name == selector or fnmatch.fnmatchcase(name, selector)
            ]
            if not matches:
                raise ManifestError(f"test selector matches nothing: {selector}")
            for name, test in matches:
                selected[name] = test
        return list(selected.values())


def _read_make_variable(path: Path, variable: str) -> List[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assignment = re.compile(rf"^\s*{re.escape(variable)}\s*(?::|\?|\+)?=\s*(.*)$")
    value_parts: List[str] = []
    collecting = False

    for raw_line in lines:
        line = raw_line.split("#", 1)[0].rstrip()
        if not collecting:
            match = assignment.match(line)
            if match is None:
                continue
            line = match.group(1).rstrip()
            collecting = True

        continued = line.endswith("\\")
        if continued:
            line = line[:-1]
        value_parts.extend(line.split())
        if not continued:
            break

    if not collecting:
        raise ManifestError(f"{path}: variable {variable} was not found")
    if not value_parts:
        raise ManifestError(f"{path}: variable {variable} is empty")
    return value_parts


def _discover_apps(repo_root: Path, spec: Mapping[str, object], timeout_s: int) -> Iterable[TestCase]:
    app_root = repo_root / str(spec.get("root", "apps"))
    excludes = {str(item) for item in spec.get("exclude", [])}
    main_files = sorted(list(app_root.rglob("main.c")) + list(app_root.rglob("main.cpp")))
    ignored_parts = {"common", "ideal_dispatcher", "riscv-tests", "third-party"}

    for main_file in main_files:
        relative = main_file.parent.relative_to(app_root)
        if any(part in ignored_parts for part in relative.parts):
            continue
        app = relative.as_posix()
        if app in excludes:
            continue
        yield TestCase(
            name=f"app:{app}",
            kind="app",
            build_target=app,
            binary=repo_root / "apps" / "bin" / app,
            testcase=relative.name,
            timeout_s=timeout_s,
        )


def _discover_rvv(repo_root: Path, spec: Mapping[str, object], timeout_s: int) -> Iterable[TestCase]:
    makefrag = repo_root / str(spec["makefrag"])
    variable = str(spec["variable"])
    for instruction in _read_make_variable(makefrag, variable):
        source = makefrag.parent / f"{instruction}.c"
        if not source.is_file():
            raise ManifestError(
                f"RVV test {instruction} is listed in {makefrag} but source is missing: {source}"
            )
        binary_name = f"rv64uv-ara-{instruction}"
        yield TestCase(
            name=f"rvv:{instruction}",
            kind="rvv",
            build_target=f"bin/{binary_name}",
            binary=repo_root / "apps" / "bin" / binary_name,
            testcase=binary_name,
            timeout_s=timeout_s,
        )


def load_catalog(repo_root: Path, manifest_path: Path) -> Catalog:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"cannot load {manifest_path}: {error}") from error

    if data.get("schema_version") != 1:
        raise ManifestError("unsupported or missing schema_version")
    defaults = data.get("defaults", {})
    timeout_s = int(defaults.get("timeout_s", 300))
    if timeout_s <= 0:
        raise ManifestError("defaults.timeout_s must be positive")

    tests: "OrderedDict[str, TestCase]" = OrderedDict()
    catalogs = data.get("catalogs", {})
    if not isinstance(catalogs, dict):
        raise ManifestError("catalogs must be an object")
    for catalog_name, spec in catalogs.items():
        if not isinstance(spec, dict):
            raise ManifestError(f"catalog {catalog_name} must be an object")
        kind = spec.get("kind")
        if kind == "app":
            discovered = _discover_apps(repo_root, spec, timeout_s)
        elif kind == "rvv":
            discovered = _discover_rvv(repo_root, spec, timeout_s)
        else:
            raise ManifestError(f"catalog {catalog_name}: unsupported kind {kind}")
        for test in discovered:
            if test.name in tests:
                raise ManifestError(f"duplicate test name: {test.name}")
            tests[test.name] = test

    suites = data.get("suites", {})
    if not isinstance(suites, dict) or not suites:
        raise ManifestError("suites must be a non-empty object")
    catalog = Catalog(tests=tests, suites=suites)
    for suite_name in suites:
        catalog.resolve_suite(suite_name)
    return catalog
