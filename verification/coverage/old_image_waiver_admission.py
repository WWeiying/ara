#!/usr/bin/env python3
"""Offline687 admission and an in-memory bridge to the sealed operand workflow.

No EDA/run command or approval issuer exists here. Historical paths containing
`..` remain literal hash keys: do not feed them to NativeHashSession.absolute.
All aliases are resolved, topology-bound, conflict-checked and rehashed uncached.
`check` prints evidence only; it does not qualify native1144 or apply exclusions.
The bridge is process-local and must not be used concurrently with other hooks.
"""
import argparse
from contextlib import contextmanager, ExitStack
import copy
import hashlib
import json
from pathlib import Path
import re
import signal
import stat
import struct
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
import run_gap74_native_offline as old
import run_gap75_operand_batch as helpers
import coverage_bitmap_delta as bitmaps

ROOT, OUT, HERE = old.ROOT, old.OUT, old.HERE
CURRENT = OUT / "gap80-old-image-20261006-01"
SCHEMA = "old-image-waiver687-admission-v1"
SCRIPT = Path(__file__).resolve()
TEST = HERE / "test_old_image_waiver_admission.py"
require = old.prior.require
SHA_RE = re.compile(r"[0-9a-f]{64}")
EXTENSIONS = (
    (76, tuple("vgap76_" + op + sew for op in ("mul", "add", "sub", "red")
               for sew in ("16", "32")) + tuple(helpers.NAMES), 669),
    (77, ("vgap77_onehot16", "vgap77_onehot32", "vgap77_dense16", "vgap77_dense32"), 673),
    (78, ("vgap78_add16", "vgap78_add32", "vgap78_sub16", "vgap78_sub32"), 677),
    (79, ("vgap79_add16", "vgap79_add32", "vgap79_add64", "vgap79_mul16",
          "vgap79_mul32", "vgap79_mul64", "vgap79_wide16", "vgap79_wide32"), 685),
    (80, ("vgap80_uniform16", "vgap80_uniform32"), 687),
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


class FileSeal:
    """No content cache; retain original alias keys and every resolved binding."""
    def __init__(self):
        self.files, self.aliases, self.canonical, self.topology, self.trees = {}, {}, {}, {}, {}
        self.finished = False

    def pin(self, path, expected=None):
        require(not self.finished, "Seal already finished")
        p = Path(path)
        require(p.is_absolute(), "Absolute evidence path required")
        require(expected is None or isinstance(expected, str) and SHA_RE.fullmatch(expected),
                "Invalid expected SHA256")
        target = p.resolve(strict=True)
        require(target.is_file(), "Not regular evidence")
        from gap74_native_hash_session import file_identity, topology_key
        bound = file_identity(p)
        h = hashlib.sha256()
        with p.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        digest = h.hexdigest()
        require(file_identity(p) == bound and p.resolve(strict=True) == target,
                "Evidence changed during read")
        key, canonical = str(p), str(target)
        require(expected is None or digest == expected, "Evidence SHA differs: " + key)
        require(key not in self.files or self.files[key] == digest, "Evidence changed: " + key)
        require(key not in self.aliases or self.aliases[key] == (canonical, bound), "Alias retargeted")
        require(canonical not in self.canonical or self.canonical[canonical] == digest,
                "Conflicting canonical aliases")
        for ancestor in dict.fromkeys((*p.parents, *target.parents)):
            value = topology_key(ancestor)
            require(str(ancestor) not in self.topology or self.topology[str(ancestor)] == value,
                    "Ancestor topology changed")
            self.topology[str(ancestor)] = value
        self.files[key], self.aliases[key], self.canonical[canonical] = digest, (canonical, bound), digest
        return p

    def hashes(self, entries):
        require(isinstance(entries, dict) and entries, "Empty evidence hash map")
        for p, digest in entries.items():
            self.pin(p, digest)

    def read(self, path, expected=None):
        p = self.pin(path, expected)
        data = p.read_bytes()
        require(sha_bytes(data) == self.files[str(p)], "JSON changed during read")
        return json.loads(data)

    def tree(self, root):
        from gap74_native_hash_session import tree_snapshot
        root = Path(root)
        members = tree_snapshot(root)
        require(all(not stat.S_ISLNK(v[0][2]) for v in members.values()), "VDB symlink")
        require(all(stat.S_ISDIR(v[0][2]) or stat.S_ISREG(v[0][2]) for v in members.values()),
                "VDB special member")
        require(str(root) not in self.trees or self.trees[str(root)] == members, "VDB membership changed")
        self.trees[str(root)] = members
        for p, value in members.items():
            if stat.S_ISREG(value[0][2]):
                self.pin(p)

    def finish(self):
        from gap74_native_hash_session import topology_key, tree_snapshot
        for p, value in self.topology.items():
            require(topology_key(Path(p)) == value, "Ancestor topology changed at finish")
        for p, members in self.trees.items():
            require(tree_snapshot(Path(p)) == members, "VDB membership changed at finish")
        for p, digest in list(self.files.items()):
            self.pin(p, digest)  # Always read original spelling again, never a cache hit.
        for p, members in self.trees.items():
            require(tree_snapshot(Path(p)) == members, "VDB changed after tail rehash")
        for p, value in self.topology.items():
            require(topology_key(Path(p)) == value, "Ancestor topology changed after tail rehash")
        self.finished = True


def elf_symbols(blob):
    """Bounded ELF64 section/symbol parsing, without invoking llvm-readelf."""
    require(blob[:6] == b"\x7fELF\x02\x01" and len(blob) >= 64, "ELF64 little endian required")
    h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(h[1] == 243 and h[3] == 0x80000000 and h[10] == 64 and h[11] > 0,
            "Wrong RISC-V ELF entry/section layout")
    require(h[5] + h[11] * 64 <= len(blob), "Truncated section headers")
    sections = [struct.unpack_from("<IIQQQQIIQQ", blob, h[5] + i * 64) for i in range(h[11])]
    def data(s):
        require(s[4] + s[5] <= len(blob), "Truncated ELF section")
        return blob[s[4]:s[4] + s[5]]
    result = {}
    for s in sections:
        if s[1] != 2:
            continue
        require(s[6] < len(sections) and s[9] == 24 and s[5] % 24 == 0, "Invalid symbol table")
        names, entries = data(sections[s[6]]), data(s)
        for offset in range(0, len(entries), 24):
            n, _, _, section, value, size = struct.unpack_from("<IBBHQQ", entries, offset)
            require(n < len(names) and b"\0" in names[n:], "Invalid symbol name")
            name = names[n:names.index(0, n)].decode("ascii")
            if name in ("tohost", "g75_result") and section:
                require(name not in result and section < len(sections), "Duplicate/invalid signature symbol")
                owner = sections[section]
                require(owner[2] & 2 and owner[3] <= value and value + 8 <= owner[3] + owner[5]
                        and size in (0, 8), "Signature not in allocated eight-byte storage")
                result[name] = value
    require(set(result) == {"tohost", "g75_result"}
            and abs(result["tohost"] - result["g75_result"]) >= 8,
            "Missing/overlapping signature symbols")
    return result


def validate_comparisons(scalar, vector):
    require(scalar.get("status") in ("MATCH", "TERMINAL_TOHOST_MATCH") and scalar.get("mismatch") is None,
            "Scalar differential failed")
    require(vector.get("status") == "PASS" and vector.get("nr_lanes") == 4
            and vector.get("vlen_bits") == 1024 and type(vector.get("compared_bytes")) is int
            and vector["compared_bytes"] > 0 and vector.get("selected_index") is None
            and vector.get("first_mismatch") is None and vector.get("stopped_at_spike_index") is None,
            "Vector differential incomplete")
    for key in ("skipped_unknown_bytes", "non_bit_exact_instructions"):
        require(type(vector.get(key)) is int and vector[key] == 0, "Vector unknown/non-bit-exact bytes")
    for key in ("incomplete_requests", "unretired_requests", "trapped_requests"):
        require(vector.get(key) == [], "Vector request incomplete or trapped")


def audit_case(seal, directory, name, state_row, plan, source_pins):
    require(state_row.get("status") == "PASS" and state_row.get("directory") == str(directory)
            and state_row.get("vdb") == str(directory / "code.vdb"), "Wrong PASS producer layout")
    require(seal.read(directory / "audit.json") == state_row, "Audit/status row differs")
    elf = seal.pin(directory / "input.elf", source_pins.get(str(directory / "input.elf")))
    require(str(elf) in source_pins, "ELF missing source pin")
    symbols = elf_symbols(elf.read_bytes())
    tohost, signature = symbols["tohost"], symbols["g75_result"]
    compile_record = seal.read(directory / "compile.command.json")
    command = compile_record.get("command", [])
    source = ROOT / "apps/riscv-tests/isa/rv64uv" / (name + ".c")
    require(isinstance(command, list) and command and command[-4:] == [
                str(ROOT / "verification/tests/gap75_start.S"), str(source), "-o", str(elf)]
            and str(source) in source_pins and Path(command[0]).is_file(),
            "Compile source/compiler not pinned")
    compiler = Path(command[0])
    compiler_key = str(compiler.resolve(strict=True))
    require(compiler_key in source_pins, "Resolved compiler not source-pinned")
    seal.pin(compiler, source_pins[compiler_key])
    for option in ("--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
                   "-DG75_NO_PRINT", "-D__SPIKE__", "-DVLEN=1024", "-DNR_LANES=4",
                   "-fno-vectorize", "-fno-slp-vectorize"):
        require(command.count(option) == 1, "Wrong stimulus compile configuration")
    seal.pin(directory / "compile.log")
    rtl = seal.read(directory / "rtl.command.json")
    expected = [plan["simv"], "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
                "+PRELOAD=" + str(elf), "+TESTCASE=" + name, "+COMMIT_TOHOST=%x" % tohost,
                "+COMMIT_TRACE=" + str(directory / "commit_trace.csv"),
                "+VECTOR_TRACE=" + str(directory / "vector_trace.csv"), "-cm",
                "line+cond+fsm+tgl+branch", "-cm_dir", str(directory / "code.vdb"), "-cm_name", name]
    require(rtl == dict(command=expected, timeout_s=1800), "Foreign image/RTL command")
    spike = seal.read(directory / "spike.command.json")
    require(spike == dict(command=[str(helpers.SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b",
                "--priv=msu", "--pmpregions=0", "-l", "--log-commits", str(elf)], timeout_s=120),
            "Foreign Spike configuration")
    require(str(helpers.SPIKE) in source_pins, "Spike binary not source-pinned")
    for p in ("spike.trace", "spike.stdout", "commit_trace.csv", "vector_trace.csv", "run.vcs.log", "console.log"):
        seal.pin(directory / p)
    writes = {address: value for c in helpers.parse_spike_commits(directory / "spike.trace")
              for address, value in c.memory_accesses if value is not None}
    require(writes.get(tohost) == 1 and type(writes.get(signature)) is int
            and writes[signature] > 0 and writes.get(signature + 4) == 0, "Spike signature failed")
    scalar = helpers.compare_commit_prefix(directory / "spike.trace", directory / "commit_trace.csv",
                0x80000000, terminal_tohost_address=tohost, rvfi_store_data_layout="unshifted")
    vector = helpers.compare_vector_commits(directory / "spike.trace", directory / "commit_trace.csv",
                directory / "vector_trace.csv", 0x80000000)
    validate_comparisons(scalar, vector)
    require(encoded(scalar) == encoded(seal.read(directory / "scalar-comparison.json"))
            and encoded(vector) == encoded(seal.read(directory / "vector-comparison.json")),
            "Saved/recomputed comparison differs")
    log = (directory / "run.vcs.log").read_text()
    require(not helpers.check_contract_log(directory / "run.vcs.log")
            and "Core Test *** SUCCESS ***" in log, "DUT selfcheck/contract failed")
    require(type(state_row.get("checks")) is int and state_row["checks"] == writes[signature]
            and type(state_row.get("vector_bytes")) is int
            and state_row["vector_bytes"] == vector["compared_bytes"], "PASS counts differ")
    seal.tree(directory / "code.vdb")
    testdirs = list((directory / "code.vdb/snps/coverage/db/testdata").iterdir())
    require(len(testdirs) == 1 and testdirs[0].name == name and testdirs[0].is_dir(), "Wrong coverage test name")
    vdb = directory / "code.vdb"
    vdb_files = {p: h for p, h in seal.files.items() if Path(p).is_relative_to(vdb)}
    files = {p: h for p, h in seal.files.items()
             if Path(p).is_relative_to(directory) and not Path(p).is_relative_to(vdb)}
    require(files and vdb_files, "PASS row lacks runtime/VDB content pins")
    return dict(name=name, coverage_test=name, vdb=str(directory / "code.vdb"),
                kind="old-image-checked-v1", status="PASS", passed_only=True, vdb_valid=True,
                vdb_rejection=None, reused=False, returncode=0,
                checks=writes[signature], vector_bytes=vector["compared_bytes"],
                files=files, vdb_files=vdb_files)


def report(seal, directory, rows, design):
    target = directory / "combined-dve"
    expected = [str(design), *[r["vdb"] for r in rows]]
    for name in ("combined-inputs.txt", "combined-dve/inputs.txt"):
        require(seal.pin(directory / name).read_text().splitlines() == expected, "DVE input membership differs")
    selected = [str(Path(r["vdb"]).with_suffix("") / r["coverage_test"]) for r in rows]
    require(seal.pin(target / "selected_tests.txt").read_text().splitlines() == selected,
            "DVE selected population differs")
    diagnostic = (r"(^|\s)(Warning|Error|Fatal)([\s:-]|$)|DVE_COVERAGE_EXPORT_FAILED|"
                  r"Database mismatch|will not be merged|Version Check Error|"
                  r"(checksum mismatches|Total unmappable exclusions|Total exclusions need to review)\s*:\s*[1-9]")
    for p in (target / "launcher.log", target / "DVEfiles/dve_gui.log"):
        text = seal.pin(p).read_text()
        require(not re.search(diagnostic, text, re.I | re.M), "DVE diagnostic")
        if p.name == "dve_gui.log":
            require("DVE_COVERAGE_EXPORT_DONE" in text.splitlines(), "DVE export not finished")
    require(seal.pin(target / "diagnostics.txt").read_text() == "", "DVE diagnostics nonempty")
    require(seal.pin(target / "summary.csv").stat().st_size > 0
            and not (target / "summary.csv.partial").exists(), "Incomplete DVE report")
    waiver = seal.read(target / "waiver_status.json")
    design_file = seal.pin(design / "snps/coverage/db/design/verilog.design.xml")
    require(waiver == dict(design_sha256=seal.files[str(design_file)], policy="reviewed-v1", mode="off",
                raw_report="summary.csv", waived_report=None, status="DISABLED"), "Raw report waiver/image differs")


def extend33(seal, rows654, plan):
    require(len(rows654) == 654 and len({r["vdb"] for r in rows654}) == 654, "Strict654 prefix required")
    rows, parent = copy.deepcopy(rows654), old.CURRENT
    previous = seal.read(parent / "combined-bits.json")
    for gap, names, population in EXTENSIONS:
        directory = OUT / ("gap%d-old-image-20261006-01" % gap)
        state = seal.read(directory / "status.json")
        require(state.get("status") == "COMPLETE" and state.get("phase") == "complete"
                and state.get("coverage_status") == "COMPLETE" and state.get("image") == plan["simv"]
                and state.get("live_rtl_reverted") is False, "Incomplete/foreign old-image campaign")
        require(type(state.get("baseline_passed")) is int and state["baseline_passed"] == len(rows)
                and type(state.get("aggregate_passed")) is int and state["aggregate_passed"] == population
                and set(state.get("cases", {})) == set(names), "Wrong extension population")
        # Gap76 predates baseline_directory: its pinned654 files and ordered prefix bind ancestry.
        require(gap == 76 and "baseline_directory" not in state or state.get("baseline_directory") == str(parent),
                "Wrong extension ancestor")
        source_pins = seal.read(directory / "source-pins.json")
        require(all(source_pins.get(p) == h for p, h in plan["image"].items()), "Missing/foreign frozen image pins")
        for p in (parent / "combined-inputs.txt", parent / "combined-bits.json"):
            require(str(p) in source_pins, "Ancestor is not source-pinned")
        seal.hashes(source_pins)
        accepted = []
        for name in names:
            row = state["cases"][name]
            if name == "vgap76_red16":
                require(row.get("status") == "FAIL", "Known failure cannot be admitted")
                require(seal.read(directory / "results" / name / "audit.json") == row,
                        "Known failure audit changed")
                continue
            require(row.get("status") == "PASS", "Only exact PASS cases can extend admission")
            accepted.append(audit_case(seal, directory / "results" / name, name, row, plan, source_pins))
        require(type(state.get("new_passed")) is int and state["new_passed"] == len(accepted)
                and len(rows) + len(accepted) == population, "Wrong PASS-only increment")
        rows.extend(accepted)
        require(len({r["vdb"] for r in rows}) == population, "Duplicate VDB")
        report(seal, directory, rows, Path(plan["design_vdb"]))
        inputs = seal.pin(directory / "combined-inputs.txt")
        fresh = bitmaps.collect(inputs)
        seal.hashes(fresh["input_hashes"])
        require(fresh == seal.read(directory / "combined-bits.json"), "Full fresh bitmap differs")
        require(bitmaps.delta(previous, fresh) == seal.read(directory / "raw-bitmap-delta.json"),
                "Extension delta differs")
        previous, parent = fresh, directory
    require(len(rows) == 687 and len(rows[654:]) == 33, "Not exact654+31+2")
    return rows


def strict654(runner_sha, seal):
    runner = old.bind_runner(runner_sha)
    for p, h in {**{str(HERE / n): h for n, h in old.PROTECTED.items()},
                 **{str(old.CURRENT / n): h for n, h in old.IDENTITY.items()},
                 str(old.RUNNER): runner_sha}.items():
        seal.pin(p, h)
    # Session=None preserves every strict check, but performs uncached historical reads.
    timings, audits = [], {}
    with old.installed_hooks(runner):
        plan = old.prior.sealed.evidence.Evidence().plan(old.CURRENT)
        rows, _, pins = old.admission654(runner, runner_sha, timings, None, audits)(
            old.CURRENT, Path(plan["design_vdb"]))
    seal.hashes(pins)
    return rows, plan, timings, audits


class Adapter:
    def __init__(self, runner_sha):
        self.runner_sha, self.seal = runner_sha, FileSeal()
        self.rows = self.plan = self.collection = None
        self.admission_sha256 = self.context_sha256 = None
        self.timings, self.audits = [], {}
        self.legacy_latest = old.prior.guard.csr_guard.latest_corpus

    def latest(self, design, image, requested=None):
        base, pins = self.legacy_latest(design, image)
        require(base == old.CURRENT, "Historical completed tip changed; reconciliation required")
        records = {str(base): dict(parent=None)}
        for path in sorted(OUT.glob("*/status.json")):
            state = json.loads(path.read_bytes())
            if state.get("image") != self.plan["simv"] or state.get("coverage_status") != "COMPLETE":
                continue
            if "aggregate_passed" not in state:
                continue
            require(state.get("status") == "COMPLETE", "Contradictory completed old-image tip")
            parent = str(old.CURRENT) if path.parent.name == "gap76-old-image-20261006-01" else state.get("baseline_directory")
            require(isinstance(parent, str) and Path(parent).parent == OUT, "Unknown completed old-image ancestry")
            require((path.parent / "combined-dve/summary.csv").is_file(), "Completed tip has no raw report")
            listing = (path.parent / "combined-inputs.txt").read_text().splitlines()
            require(listing and listing[0] == str(design), "Completed old-image design drift")
            records[str(path.parent)] = dict(parent=parent)
            pins[str(path)] = sha_bytes(path.read_bytes())
            pins[str(path.parent / "combined-inputs.txt")] = sha_bytes((path.parent / "combined-inputs.txt").read_bytes())
        for value in records.values():
            require(value["parent"] is None or value["parent"] in records, "Broken completed ancestry")
        tip = Path(old.prior.guard.csr_guard.latest_tip(records))
        require(tip == CURRENT and (requested is None or Path(requested) == CURRENT),
                "687 is stale or completed tips are ambiguous")
        require(image == self.plan["image"] and str(design) == self.plan["design_vdb"], "Latest image differs")
        return tip, pins

    def admit(self):
        with old.no_tools():
            rows, self.plan, self.timings, self.audits = strict654(self.runner_sha, self.seal)
            self.rows = extend33(self.seal, rows, self.plan)
            self.seal.tree(Path(self.plan["design_vdb"]))
            for row in self.rows:
                self.seal.tree(Path(row["vdb"]))
            self.seal.pin(SCRIPT)
            self.seal.pin(TEST)
            _, census = self.latest(Path(self.plan["design_vdb"]), self.plan["image"], CURRENT)
            self.seal.hashes(census)
            self.collection = dict(schema=SCHEMA, status="PASS", passed=687, total=687,
                cross_image_reuse=False, image=self.plan["image"], baseline=str(old.CURRENT),
                reports={str(CURRENT / n): self.seal.files[str(CURRENT / n)] for n in
                         ("combined-bits.json", "combined-dve/summary.csv")},
                admission_files=dict(self.seal.files))
            self.admission_sha256 = sha_bytes(encoded(dict(rows=self.rows, plan=self.plan,
                                                           collection=self.collection)))
        return self

    @contextmanager
    def bridge(self):
        """Exact virtual reads only; neither historical ledger nor collection is rewritten."""
        require(self.collection is not None, "Must independently admit687 first")
        require(self.admission_sha256 == sha_bytes(encoded(dict(rows=self.rows, plan=self.plan,
                                                                collection=self.collection))),
                "In-memory admission changed")
        guard, workflow = old.prior.guard, old.prior.workflow
        virtual = {CURRENT / "collection.json": self.collection,
                   CURRENT / "all-passed-outcomes.json": self.rows,
                   CURRENT / "plan.json": self.plan}
        def reader(original):
            def read(path):
                return copy.deepcopy(virtual[Path(path)]) if Path(path) in virtual else original(path)
            return read
        actual_sha = guard.csr_guard.sha
        def digest(path):
            if Path(path) == CURRENT / "collection.json":
                return sha_bytes(encoded(self.collection))
            return actual_sha(path)
        original_admit = guard.csr_guard.legacy.admitted_inputs
        def admitted(baseline, design):
            if baseline != CURRENT:
                return original_admit(baseline, design)
            require(str(design) == self.plan["design_vdb"], "Admission design differs")
            return copy.deepcopy(self.rows), CURRENT / "combined-dve/inputs.txt", dict(self.seal.files)
        with ExitStack() as stack:
            stack.enter_context(patch.object(guard.csr_guard, "latest_corpus", self.latest))
            stack.enter_context(patch.object(guard.csr_guard, "jread", reader(guard.csr_guard.jread)))
            stack.enter_context(patch.object(guard.csr_guard, "sha", digest))
            stack.enter_context(patch.object(workflow, "jread", reader(workflow.jread)))
            stack.enter_context(patch.object(guard.csr_guard.legacy, "admitted_inputs", admitted))
            yield

    def build_context(self):
        require(not self.seal.finished, "A finished admission is not a reusable oracle cache")
        if self.rows is None:
            self.admit()
        with old.no_tools(), self.bridge():
            context = old.prior.guard.build_context(CURRENT)
        require(context["tests"] == 687 and len(context["policy"]["allowed_points"]) == 201
                and len(context["operand_targets"]) == 1144 and len(context["observers"]) == 10,
                "Composed scope changed")
        context["old_image_admission"] = dict(schema=SCHEMA, baseline=str(CURRENT),
            strict_prefix=654, independently_replayed_new_pass=33,
            collection_basis="in-memory seal of real evidence; not a historical collection file",
            native_qualified=False, exclusions_applied=False, oracle_cached=False)
        self.seal.hashes(context["pins"])
        self.seal.finish()
        _, census = self.latest(Path(context["design"]), context["image"], CURRENT)
        require(all(context["pins"].get(p) == h for p, h in census.items()), "Tip changed after tail rehash")
        self.context_sha256 = sha_bytes(encoded(context))
        return context

    def capture_snapshot(self, output, context):
        """Future explicit offline preparation only, never a launch or receipt.

        Call once with the context returned by this same build_context invocation.
        A newer tip or changed input rejects; partially emitted manifests are
        invalidated. Direct use of the historical CLI still rejects virtual687.
        """
        require(self.seal.finished and context.get("old_image_admission", {}).get("schema") == SCHEMA
                and context.get("baseline") == str(CURRENT)
                and context.get("baseline_collection_sha256") == sha_bytes(encoded(self.collection))
                and self.context_sha256 == sha_bytes(encoded(context)),
                "Qualified same-invocation context required")
        output, bundle = old.prior.workflow.locations(output)
        require(not output.exists() and not bundle.exists(), "Fresh capture output required")
        from gap74_native_hash_session import topology_key, tree_snapshot
        def unchanged():
            for p, value in self.seal.topology.items():
                require(topology_key(Path(p)) == value, "Prepared ancestor topology changed")
            for p, members in self.seal.trees.items():
                require(tree_snapshot(Path(p)) == members, "Prepared VDB membership changed")
            fresh = FileSeal()
            fresh.hashes(self.seal.files)
            fresh.hashes(context["pins"])
            fresh.finish()
            _, census = self.latest(Path(context["design"]), context["image"], CURRENT)
            require(all(context["pins"].get(p) == h for p, h in census.items()), "Prepared census changed")
        with old.no_tools():
            unchanged()
            try:
                with self.bridge():
                    result = old.prior.workflow.snapshot(output, copy.deepcopy(context), "capture")
                unchanged()
                return result
            except BaseException:
                manifest = bundle / "snapshot.json"
                if manifest.is_file():
                    manifest.rename(bundle / "unqualified-snapshot.json")
                raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--baseline", type=Path, default=CURRENT)
    parser.add_argument("--closure91-sha256", required=True)
    args = parser.parse_args(argv)
    require(args.baseline.resolve(strict=True) == CURRENT, "Only exact gap80/687 supported")
    def expired(signum, frame):
        raise TimeoutError("300s offline bound; no retry or EDA")
    handler = signal.signal(signal.SIGALRM, expired)
    signal.alarm(300)
    try:
        adapter = Adapter(args.closure91_sha256)
        context = adapter.build_context()
        print(json.dumps(dict(status="OFFLINE687_ADMITTED_NOT_NATIVE_QUALIFIED", schema=SCHEMA,
            baseline=str(CURRENT), tests=687, strict_prefix=654, new_pass=33,
            baseline_collection_sha256=context["baseline_collection_sha256"],
            source_sha256=adapter.seal.files[str(SCRIPT)], files=context["pins"],
            topology=adapter.seal.topology, aliases=adapter.seal.aliases,
            stage_timings=adapter.timings, row_audit_costs=adapter.audits,
            tools_launched=False, receipt_created=False, exclusions_applied=False), indent=2))
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, handler)


if __name__ == "__main__":
    main()
