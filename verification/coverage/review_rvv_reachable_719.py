"""Read-only RVV boundary shortlist against sealed719; no build, simulator or EDA."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

from inventory_operand_debug import Design, points
from closure_point_inventory import definition, read_xml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"
BASE = OUT / "gap102b-offline-admitted-719-20261006-01"
SEAL = "0edf5405a8139eea50d82af6181f7d53ccb70699c2b232c8e3001add0ec242bb"
VDB = OUT / "repaired-aligned-build-20260930-01/sim/simv.vdb"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher"
OBJDUMP = Path("/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-objdump")


def sha(path):
    with Path(path).open("rb") as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def require(ok, why):
    if not ok:
        raise ValueError(why)


def arith(func6, form, vs2, rs1):
    return (func6 << 26) | (1 << 25) | (vs2 << 20) | (rs1 << 15) | (form << 12) | (16 << 7) | 0x57


def memory(store, width, nf=0, whole=False):
    return (nf << 29) | (1 << 25) | ((8 if whole else 0) << 20) | (10 << 15) | (width << 12) | (8 << 7) | (0x27 if store else 7)


def specifications():
    tests = []
    for name, func6 in (("vnsrl", 44), ("vnsra", 45)):
        for suffix, form, operand in (("wv", 0, 24), ("wx", 4, 7), ("wi", 3, 1)):
            for sew, lmul, vs2, boundary in ((64, "m1", 8, "source EEW128"),
                    (8, "m1", 9, "source EMUL2 odd base"), (8, "m2", 10, "source EMUL4 base mod4=2"),
                    (8, "m4", 12, "source EMUL8 base mod8=4")):
                tests.append(dict(instruction=f"{name}.{suffix} v16,v{vs2}," +
                    (f"v{operand}" if form == 0 else ("x7" if form == 4 else "1")),
                    word=f"0x{arith(func6, form, vs2, operand):08x}", sew=sew, lmul=lmul,
                    vl=4, vstart=1, boundary=boundary))
    return [dict(id="R1", title="整数窄化移位三种形式的宽度/源组对齐", priority=1,
        lines=[1925,1929,1930,1931,1943,1947,1948,1949,2217,2221,2223,2224,
               2235,2239,2240,2241,2477,2481,2482,2483,2495,2499,2500,2501], tests=tests,
        chain="CVA6 OpcodeVec -> OPIVV/OPIVX/OPIVI -> VNSRL/VNSRA -> EEW>32或vs2组对齐拒绝 -> illegal_insn -> cause2；不得进入operand requester/queue/ALU。",
        condition="rd=v16，vv的vs1=v24保持LMUL对齐；vm=1，不读mask；仅切换SEW/LMUL/宽源组基址；x7=1。24个拒绝点可共享一次初始化与最终VRF读回。",
        recovery="e8,m1,VL4,vstart0；vadd.vx v16,v8,x7，逐字节模256相加C oracle；不要用carry/slide/FP16或合法narrow作为恢复。",
        estimate_seconds=[60,180]),
      dict(id="R2", title="普通unit-stride访存EMUL下溢/上溢", priority=2,
        lines=[4236,4493,4500], predicate_lines=[4235,4492,4499],
        tests=[dict(instruction="vle8.v v8,(a0)",word=f"0x{memory(False,0):08x}",sew=64,lmul="mf8",vl=1,vstart=0,boundary="EMUL=1/64 < 1/8"),
               dict(instruction="vse8.v v8,(a0)",word=f"0x{memory(True,0):08x}",sew=64,lmul="mf8",vl=1,vstart=0,boundary="EMUL=1/64 < 1/8"),
               dict(instruction="vse64.v v8,(a0)",word=f"0x{memory(True,7):08x}",sew=8,lmul="m8",vl=4,vstart=0,boundary="EMUL=64 > 8")],
        chain="CVA6 LoadFp/StoreFp width -> Ara普通unit-stride decode -> EMUL=LMUL*EEW/SEW -> sign-transition与EEW差值拒绝 -> illegal_insn_load/store -> cause2；不得进入VLSU或产生访存。",
        condition="所有vtype本身合法且VL非零；a0指向对齐的有效guard buffer，排除地址fault；nf=0、mop=00、lumop/sumop=0、vm=1。",
        recovery="e8,m1，VL4；合法vle8.v/vse8.v到单独缓冲；C完整字节相等+前后guard不变。",
        estimate_seconds=[40,100]),
      dict(id="R3", title="whole-register load/store的保留NF=2", priority=3,
        lines=[4320,4580], branch_raw=[390,336],
        tests=[dict(instruction="reserved whole-register load .word",word=f"0x{memory(False,0,2,True):08x}",sew=8,lmul="m1",vl=4,vstart=0,boundary="nf=2表示3寄存器，非0/1/3/7"),
               dict(instruction="reserved whole-register store .word",word=f"0x{memory(True,0,2,True):08x}",sew=8,lmul="m1",vl=4,vstart=0,boundary="nf=2表示3寄存器，非0/1/3/7")],
        chain="CVA6普通memory width允许且不检查NF -> VLE/VSE whole-register -> nf case default -> illegal_insn_load/store -> cause2；不等同segment，也不得送VLSU。",
        condition="EEW8、v8对齐、有效a0、vm=1、mop=00、lumop/sumop=01000；保留default是可达拒绝路径，必须测试并保护。",
        recovery="合法vl1re8.v v8,(a0)后vs1r.v到独立缓冲；128字节C oracle与guard。",
        estimate_seconds=[40,100])]


def build():
    pins = {}
    def pin(path, expected=None):
        p = Path(path).absolute(); h = sha(p)
        require(expected is None or h == expected, "pin differs: " + str(p))
        require(str(p) not in pins or pins[str(p)] == h, "pin conflict")
        pins[str(p)] = h
        return p
    manifest = json.loads(pin(BASE / "admission-manifest.json", SEAL).read_text())
    for name in ("combined-bits.json", "combined-inputs.txt", "evidence-pins.json", "status.json"):
        p = BASE / name; pin(p, manifest["output_pins"][str(p)])
    bits = json.loads((BASE / "combined-bits.json").read_text())
    require(len(bits["tests"]) == len(set(bits["tests"])) == 719, "not exact719")
    design = Design(VDB)
    for rel, h in bits["design"].items(): pin(design.db / rel, h)
    sourcepins = json.loads(pin(OUT / "repaired-aligned-build-20260930-01/build-source-pins.json").read_text())
    frozen = pin(OUT / "old-image-source-evidence-20261006-01/ara_dispatcher.sv",
                 sourcepins[str(ROOT / "hardware/src/ara_dispatcher.sv")])
    for rel in ("cva6_accel_first_pass_decoder.sv", "ara_sequencer.sv", "lane/operand_queue.sv", "lane/operand_queues_stage.sv"):
        p = ROOT / "hardware/src" / rel; pin(p, sourcepins[str(p)])
    for rel in ("vopivx_vsbc_vd0.c", "vregister_group_illegal.c", "vnsrl.c", "vnsra.c", "vl1r.c", "vle8.c", "vse8.c", "vse64.c"):
        p = ROOT / "apps/riscv-tests/isa/rv64uv" / rel
        if p.exists(): pin(p)
    for rel in ("verification/tests/gap75_start.S", "verification/tests/gap75.ld",
                "verification/coverage/collect_opivx_vsbc_strict.py", "verification/coverage/build_opivx_vsbc_preflight.py",
                "verification/coverage/inventory_operand_debug.py", "verification/coverage/closure_point_inventory.py",
                "verification/coverage/reviewed_20261004/audit_readonly.py"):
        pin(ROOT / rel)
    pin(Path(__file__).resolve()); pin(OBJDUMP); pin(OBJDUMP.resolve())
    allpoints = {}
    for metric in ("line", "branch", "cond"):
        r = bits["metrics"][metric][SCOPE]
        node = (definition(read_xml(design.db / "shape/cond.verilog.shape.xml"), design.hierarchy[SCOPE], r["checksum"])
                if metric == "cond" else design.definition(SCOPE, metric))
        allpoints[metric] = [p for p in points(metric, node, r["width"])
                            if not int(r["bits"], 16) & (1 << (r["width"] - 1 - p["raw_index"]))]
    candidates = specifications()
    for candidate in candidates:
        selected = []; locations = set(candidate.get("predicate_lines", candidate["lines"]))
        for metric, ps in allpoints.items():
            for p in ps:
                if metric == "line": take = int(p["line"]) in candidate["lines"] and "illegal_insn" in p["expression"]
                elif metric == "branch":
                    take = (p["raw_index"] in candidate.get("branch_raw", []) or any(
                        int(e["id"]) in locations and p["native_vector"]["vector"][-int(e["index"])] == "1"
                        for e in p["expressions"]))
                else: take = p["line"].isdigit() and int(p["line"]) in locations and p["vector"] == "1"
                if take:
                    r = bits["metrics"][metric][SCOPE]
                    selected.append(dict(metric=metric, scope=SCOPE, bitmap_width=r["width"],
                        metric_checksum=r["checksum"], hit719=False, frozen_source=str(frozen), point=p))
        candidate["zero_targets"] = selected
        candidate["estimated_new_target_ceiling"] = dict(Counter(p["metric"] for p in selected))
        candidate["estimate_is_not_measured_or_guaranteed"] = True
        require(any(p["metric"] == "line" for p in selected), "no remaining line gain")
    words = {int(t["word"],16) for c in candidates for t in c["tests"]}
    matches = {w: [] for w in words}; cache = {}
    basepins = json.loads((BASE / "evidence-pins.json").read_text())
    for p, h in basepins.items():
        if not p.endswith(".elf"): continue
        pin(p, h)
        if h not in cache:
            output = subprocess.run([str(OBJDUMP), "-d", p], check=True, capture_output=True).stdout.decode("utf-8", "strict")
            found = set()
            for line in output.splitlines():
                m = re.match(r"\s*([0-9a-f]+):\s+(.*)", line)
                if not m: continue
                tokens = m[2].split()
                if len(tokens)>=4 and all(re.fullmatch(r"[0-9a-f]{2}",v) for v in tokens[:4]):
                    w = int.from_bytes(bytes.fromhex(" ".join(tokens[:4])),"little")
                elif tokens and re.fullmatch(r"[0-9a-f]{8}",tokens[0]): w=int(tokens[0],16)
                else: continue
                if w in words: found.add(w)
            cache[h] = found
        for w in cache[h]: matches[w].append(p)
    for c in candidates:
        for t in c["tests"]: t["existing_admitted_elf_word_matches"] = matches[int(t["word"],16)]
        c["dedup_limit"] = "全719 evidence-pins中ELF逐个非ZCC LLVM静态反汇编；同instruction word可能用于合法SEW/LMUL。word存在不等于相同上下文；719目标零证明该编译覆盖路径尚未纳入。新case尚无ELF，不声称完整ELF去重已通过。"
    report = dict(status="STATIC_CANDIDATES_ONLY_NOT_RUN_NOT_ADMITTED_NOT_WAIVED", baseline=719,
        baseline_path=str(BASE), baseline_manifest_seal=SEAL, candidates=candidates,
        summary="优先R1，一次24个短拒绝点；次选R2三点。均为ordinary RVV前端边界，不是queue/backend正向新增；不混入carry/slide/FP16已知bug路径。",
        queue_screening="复核lane0 ALU/MFPU队列源码与719零点：未得到同时满足producer、cmd.conv、实例参数、state的高收益正向新路径证明。已知protected252维持保护；不重跑VL257诊断，不以零覆盖waive。sequencer raw134要求narrow count>=8，普通合法narrow源组约束不支持据此保证命中；raw70是debug plusarg，raw36/75是LSU异常路径，不列为收益。",
        oracle="复用已核VSBC的gap75 CRT/mscratch保存型trap handler及完整Spike scalar/vector strict checker；每个标号fault唯一cause2、mtval精确word、mepc精确标号、仅+4返回。逐点捕获vstart/vtype/vl/vcsr/fcsr与handler side effects；VRF预种并完整dump含guard。bad arch_seq backend uops=0、VRF writes=0、访存issue=0，单独合法恢复C oracle与Spike完全差分，skip0。现有vregister_group_illegal的裸t0/t1 handler不能直接用于严格副作用证明。",
        launch_gate="父侧选case后再prepare源/ELF/host/Spike及旧simv66 pins；构建仅非ZCC LLVM。静态剩余目标绑定不替代实际PASS/oracle/rawdelta；仿真FAIL只记录，不修RTL。",
        timing="预计秒数仅按已有单VSBC CPU47.630s量级估计，未测量；不授权自动launch。",
        native_DVE_qualification=False, raw_indices_are_DVE_selectors=False, exclusions_created=False,
        simulations_started=False, rtl_changed=False, elfs_scanned=sum(p.endswith('.elf') for p in basepins),
        unique_elf_hashes_scanned=len(cache), pins=pins)
    for p,h in pins.items():require(sha(p)==h,"input changed during review")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); out=a.output.absolute()
    require(out.parent==OUT and not out.exists(),"fresh report required")
    report=build()
    with out.open('x') as stream: json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    seal=sha(out)
    with out.with_suffix('.seal.json').open('x') as stream:
        json.dump({str(out):seal},stream,indent=2);stream.write('\n')
    print(json.dumps(dict(report=str(out),seal=seal,pins=len(report['pins']),elfs=report['elfs_scanned'],
        candidates=[dict(id=c['id'],targets=c['estimated_new_target_ceiling']) for c in report['candidates']])))


if __name__=='__main__':main()
