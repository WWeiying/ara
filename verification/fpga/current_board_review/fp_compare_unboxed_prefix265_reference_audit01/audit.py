#!/usr/bin/env python3
"""One offline audit of the sealed reference. Never execute its producers."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / "fp_compare_unboxed_prefix265_prepare01"
READY_SHA = "ee10a401774a5cb474be69c317edad4ea052c147a42b5fd03aa4cc4b1f5db731"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def save(name, data):
    with (HERE / name).open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def main():
    require(sha(REF / "READY.json") == READY_SHA, "Sealed READY drift")
    ready = read(REF / "READY.json")
    scope = dict(calls=265, predecessors=264, capacity=16, result_bits=4240, guards=530, vstart=265, flags=265)
    require(ready["scope"] == scope and ready["attempts"] == 1 and ready["retries"] == 0 and
            ready["dut_pass"] is False and ready["full_parent_pass"] is False, "Sealed exact scope")
    pins = {str(REF / "READY.json"): READY_SHA}
    for group in (ready["baseline_pins"], ready["owned_pins"], read(REF / "reference01/input_pins.json")):
        for path, digest in group.items():
            require(path not in pins or pins[path] == digest, "Conflicting pin")
            pins[path] = digest
    for path, digest in pins.items():
        require(sha(path) == digest, "Input drift: " + path)
    sys.path.insert(0, str(REF))
    import software_prepare as producer
    import strict
    proof = read(REF / "source_elf_proof.json")
    original = REF / "software/original"
    source = producer.SOURCE.read_text()
    require(source == (original / "parent.c").read_text(), "Original C copy")
    anchor = "        ++cases;\n    }\n"
    require(source.count(anchor) == 1, "Original boundary")
    prefix = source.replace(anchor, "        ++cases;\n        if(cases==265)goto prefix_done;\n    }\nprefix_done:\n")
    require(prefix == (REF / "software/prefix.c").read_text() and
            producer.base.adapt(prefix, producer.NAME) == (REF / "software/case.c").read_text(), "Only approved prefix/wrapper diff")
    oracle = source[source.index("        if((uint32_t)status)"):source.index("        ++cases;")]
    require(oracle in (REF / "software/case.c").read_text() and
            hashlib.sha256(oracle.encode()).hexdigest() == proof["oracle_sha256"], "Full original oracle")
    require(proof["defines"] == producer.DEFS and proof["original_rebuild_byte_identical"] is True and
            sha(producer.OLD) == sha(REF / "software/original_rebuilt.elf") == proof["original_elf"]["sha256"] ==
            "404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152", "Original Linux ELF identity")
    old, _ = producer.disassemble(producer.OLD)
    specs = {}
    starts = [0x10540+64*i for i in range(4)] + [0x10640+72*i for i in range(6)]
    for backend in ("soc", "spike"):
        elf = Path(proof[backend + "_elf"]["path"])
        require(sha(elf) == proof[backend + "_elf"]["sha256"] == ready[backend + "_elf"]["sha256"], "Executed ELF identity")
        spec = strict.specification(elf, backend == "spike")
        for op, start in enumerate(starts):
            for instruction in spec["routines"][op]:
                require(old["code"][format(start, "x")]["insn"] == instruction["insn"], "Original helper machine bytes")
                start += len(instruction["insn"]) // 2
        require([i["insn"] for i in spec["capacity"]] == ["52fd", "00e2f557", "8082"], "Original capacity")
        specs[backend] = spec
    # Original fixture initializer consists only of numeric brace lists; parse as JSON arrays.
    fixture = (original / "fixtures.h").read_text()
    literal = re.search(r"expected\[6\]\[16\]\[16\]=([^;]+);", fixture).group(1)
    require(re.fullmatch(r"[{},0-9\s]+", literal) is not None, "Fixture literal grammar")
    table = json.loads(literal.replace("{", "[").replace("}", "]"))
    inputs = [int(n, 16) for n in re.findall(r"UINT64_C\(0x([0-9a-f]+)\)", fixture)]
    require(len(inputs) == 16 and len(table) == 6 and all(len(x) == 16 and all(len(y) == 16 for y in x) for x in table), "Full fixtures")
    golds = []
    for seed, op, vl, mode, sticky in itertools.product(range(32), range(10), (0,1,2,3,8,15,16), range(4), range(2)):
        ai = [(i+seed+7*(seed//16)) % 16 for i in range(16)]
        bi = [(i*3+seed*5+seed//16) % 16 if op < 4 else seed % 16 for i in range(16)]
        flags, allowed = sticky, []
        for i in range(16):
            bit, nv = table[op if op < 4 else op-4][ai[i]][bi[i] if op < 4 else 14]
            oldbit = (91 >> (i % 8)) & 1
            allowed.append([bit] if i < vl else [oldbit] if vl == 0 else sorted({oldbit, 1, bit}))
            if i < vl:
                flags |= nv
        golds.append(dict(ordinal=len(golds)+1, seed=seed, op=op, vl=vl, mode=mode, sticky=sticky, vstart=0,
            a=[inputs[i] for i in ai], b=[inputs[i] for i in bi], mask=[(255,170,36,0)[mode]]*128, allowed=allowed, flags=flags))
        if len(golds) == 265:
            break
    require(read(REF / "model.json") == dict(rows=golds, calls=265, capacity=16, predecessors=264, result_bits=4240, guards=530), "Original fixture vs complete model")
    cmd = read(REF / "reference01/command.json")
    execution = read(REF / "reference01/execution.json")
    stored = read(REF / "reference01/result.json")
    expected_cmd = [str(producer.base.SPIKE), "-d", "--debug-cmd="+str(REF / "reference01/spike.cmd"),
        "--isa=rv64gcv_zfh_zvfh_zvl1024b", "-m2", "--log-commits", "--log="+str(REF / "reference01/commits.log"), proof["spike_elf"]["path"]]
    require(cmd["command"] == expected_cmd and cmd["max_steps"] == 2000000 and cmd["max_bytes"] == 268435456 and
            cmd["timeout_s"] == 120 and cmd["attempt"] == 1 and cmd["retry"] is False, "Actual profile/limits")
    require(type(execution["returncode"]) is int and execution["returncode"] == stored["returncode"] == 0 and
            execution["elapsed_s"] == stored["elapsed_s"] < 120, "Actual reference rc/budget")
    require(not strict.VETO.search((REF / "reference01/spike.log").read_text()) and not (REF / "reference01/not_accepted.json").exists(), "Reference error veto")
    require(sha(REF / "reference01/result.json") == ready["reference_sha256"], "Stored result pin")
    spec = specs["spike"]
    lookup = {i["pc"]: (op, n) for op, rr in enumerate(spec["routines"]) for n, i in enumerate(rr)}
    evidence = dict(actual_fmv_d_x=[], final={})

    def observed():
        call, fp, vectors = 0, {}, {}
        for line, row in enumerate(strict.spike_rows(REF / "reference01/commits.log"), 6):
            pair = lookup.get(row["pc"])
            if pair is not None and pair[1] == 0:
                call += 1
            fp.update(row["fp"])
            vectors.update(row["vectors"])
            if pair == (4, 7):
                require(0 in row["fp"] and row["fp"][0] == 0, "Missing actual raw fmv.d.x f0=0")
                evidence["actual_fmv_d_x"].append(dict(call=call, raw_line=line, pc=hex(row["pc"]), encoding="f2038053", actual_ft0=hex(fp[0])))
            if call == 265 and pair == (4, 10):
                require(fp.get(0) == 0 and vectors[8] >> 224 & 65535 == 0x7e55 and vectors[8] >> 240 & 65535 == 0x7c55 and
                        vectors[24] & 0x7fff == 0, "Actual final scalar/source/result discriminator")
                evidence["final"].update(target_raw_line=line, target_pc=hex(row["pc"]), actual_ft0=hex(fp[0]),
                    active_qnan=hex(vectors[8] >> 224 & 65535), tail_snan=hex(vectors[8] >> 240 & 65535), actual_result16=hex(vectors[24]&65535))
            if call == 265 and pair in ((4, 11), (4, 12)):
                require(row["value"] == 0, "Actual final vstart/flags")
                evidence["final"]["returned_vstart" if pair[1] == 11 else "returned_flags"] = dict(value=0, raw_line=line, pc=hex(row["pc"]))
            yield row

    print("START_ONE_COMPLETE_OFFLINE_RAW_AUDIT", flush=True)
    start = time.monotonic()
    raw = strict.audit(observed(), spec, True)
    save("recomputed_reference.json", raw)
    require(raw == {k:v for k,v in stored.items() if k not in ("elapsed_s", "returncode", "raw_sha256", "raw_bytes", "actual_isa")}, "Complete raw vs stored structure")
    expected = dict(target_calls=265, full_result_bit_checks=4240, guard_checks=530, returned_vstart_zero=265,
        returned_flags_checked=265, helper_instructions=4587, actual_initialization_stores=76850,
        unused_helper_retirements=0, firmware_retired_to_exit=701895, retired=704995, park_retired=3100)
    require(all(raw[k] == v for k,v in expected.items()) and len(evidence["actual_fmv_d_x"]) == 41, "Full exact raw counts/scalar transport")
    require(not strict.VETO.search(raw["reconstructed_console"]) and all(raw["reconstructed_console"].count(m) == 1 for m in proof["spike_elf"]["pass_markers"]), "Actual complete console oracle")
    require(raw["calls"][-1]["ordinal"] == 265 and raw["calls"][-1]["op"] == 4 and raw["calls"][-1]["vl"] == 15 and
            raw["calls"][-1]["sticky"] == raw["calls"][-1]["mode"] == 0, "Final original tuple")
    rawpath = REF / "reference01/commits.log"
    require(sha(rawpath) == ready["raw_sha256"] == stored["raw_sha256"] and rawpath.stat().st_size == stored["raw_bytes"] == 45935822,
            "Raw reference identity/size")
    for path, digest in pins.items():
        require(sha(path) == digest, "Post-audit input drift: " + path)
    save("actual_evidence.json", evidence)
    for path in (HERE / "audit.py", HERE / "recomputed_reference.json", HERE / "actual_evidence.json"):
        pins[str(path)] = sha(path)
    audit = dict(status="ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT", scope=scope, ready_sha256=READY_SHA,
        program=producer.NAME, original_linux_rebuild_byte_identical=True, original_elf=proof["original_elf"],
        soc_elf=proof["soc_elf"], spike_elf=proof["spike_elf"], actual_isa=cmd["actual_isa"], actual_reference_rc=0,
        reference_elapsed_s=execution["elapsed_s"], retired=701895, reference_counts=expected, reset_rom_retired=5, total_raw_records=705000,
        actual_unboxed_fmv_d_x=41, scalar_target_ft0=0, final=evidence["final"], full_original_tail_oracle=True,
        full_original_fixture_model_matches=True, raw_recomputed_once=True, raw_equals_stored=True,
        original_artifacts_unchanged=True, recompute_seconds=time.monotonic()-start, attempts=1, retries=0,
        DUT_or_Host_or_reference_rerun=False, producer_edits=False, DUT_accepted=False, full17920_accepted=False,
        original_linux_execution_accepted=False, current_RTL_bug_proven=False, pins=pins)
    save("audit.json", audit)
    pins[str(HERE / "audit.json")] = sha(HERE / "audit.json")
    admission = dict(schema_version=1, status="ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT", program=producer.NAME,
        prepared_directory=str(REF), ready_sha256=READY_SHA, independent_audit_path=str(HERE / "audit.json"),
        independent_audit_sha256=sha(HERE / "audit.json"), scope=scope, soc_elf=proof["soc_elf"], spike_elf=proof["spike_elf"],
        original_elf=proof["original_elf"], reference_raw_sha256=stored["raw_sha256"], actual_isa=cmd["actual_isa"],
        reference_rc=0, firmware_retired=701895, scalar_raw_ft0=0, original_unboxed_moves=41,
        intended_configuration=dict(nr_lanes=4, vlen=1024, fp16=True), launch_authorized=False,
        requires_separate_frozen_image_worker_review_and_parent_authorization=True, DUT_accepted=False,
        full_parent_accepted=False, original_linux_execution_accepted=False, pins=pins)
    save("admission.json", admission)
    print(json.dumps(dict(status=audit["status"], scope=scope, raw_equals_stored=True, original_artifacts_unchanged=True,
        actual_fmv_d_x=41, pins=len(pins), admission_sha256=sha(HERE / "admission.json"))), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        save("NOT_ACCEPTED.json", dict(status="NOT_ACCEPTED", error=repr(error), no_rerun=True))
        raise
