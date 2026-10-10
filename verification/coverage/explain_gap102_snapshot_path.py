"""Offline observed GAP102 route attribution; no waiver or admission proof."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import run_gap102_simulation as r
import coverage_bitmap_delta as bitmap
from closure_point_inventory import points
from calibrate_gap102_branch_path import expression_bit

OUT = r.life.OUT
RUN = OUT / "gap102-widen-acc-cross-old-image-20261006-02"
CANDIDATE = OUT / "gap102-strict-candidate-717-20261006-02"


def hit(record, raw):
    r.proof.require(type(raw) is int and 0 <= raw < record["width"], "Raw index out of range")
    return bool(int(record["bits"],16) & (1 << (record["width"]-1-raw)))


def active_regs(base, eew, start, vl, count):
    return [base+i for i in range(count) if vl>start and start < ((i+1)*128 >> eew)
            and vl > (i*128 >> eew)]


def explain():
    pins = {}
    def read(path, expected=None):
        path = Path(path).absolute()
        r.proof.require(path.resolve()==path and not path.is_symlink(), "Aliased evidence")
        raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
        r.proof.require(expected is None or expected==digest,"Expected input differs: "+str(path))
        pins.update(r.life.merge_pins(pins,{str(path):digest}))
        return raw
    runtime = json.loads(read(RUN/"manifest.json"))
    r.proof.require(runtime == json.loads(read(RUN.with_name(RUN.name+".prepared.json"),
        "7c9aed3b60eb2249e8555547bc81ac7d7b3b2e647fdbb4a01b35483aab6b4280")),"Reviewed attempt02 differs")
    buildpin= r.proof.old.BUILD/"build-source-pins.json"
    sources=json.loads(read(buildpin,runtime["pins"][str(buildpin)]))
    source=OUT/"old-image-source-evidence-20261006-01/ara_dispatcher.sv"
    text=read(source,"9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43").decode()
    r.proof.require(pins[str(source)] == sources[str(r.proof.ROOT/"hardware/src/ara_dispatcher.sv")],
                    "Historical dispatcher pin differs")
    for name in ("hardware/tb/ara_commit_monitor.sv","hardware/src/ara_system.sv"):
        path=r.proof.ROOT/name;read(path,sources[str(path)])
    for token in ("source_snapshot_resolves_widen = source_snapshot_valid_q &&",
                  "source_snapshot_replays_wide_vd = source_snapshot_valid_q &&",
                  "!source_snapshot_resolves_widen ||",
                  "source_snapshot_replays_wide_vd", "maintenance_req.source_snapshot_capture = 1'b1;",
                  "if (unsigned'(ara_req.vl) <= overlap_start_element)"):
        r.proof.require(token in text,"Frozen source contract missing: "+token)
    manifest=json.loads(read(r.proof.BASE/"admission-manifest.json",r.proof.BASE_SEAL))
    before=json.loads(read(r.proof.BASE/"combined-bits.json",manifest["output_pins"][str(r.proof.BASE/"combined-bits.json")]))
    single=json.loads(read(CANDIDATE/"single-raw-bits.json"))
    read(CANDIDATE/"diagnostic-inputs.txt")
    r.proof.require(bitmap.collect(CANDIDATE/"diagnostic-inputs.txt")==single,"Actual raw VDB differs")
    delta=bitmap.delta(before,bitmap.combine(before,single))
    r.proof.require(delta["metrics"]==dict(line=0,cond=0,branch=0,fsm=0),"Not zero increment")
    read(CANDIDATE/"failure.json");read(CANDIDATE/"raw-bitmap-delta.json")
    for name in ("scalar-comparison.json","vector-comparison.json","observed-data.json","lifecycle.json"):
        read(CANDIDATE/name)
    for path,h in single["input_hashes"].items(): read(Path(path),h)
    design=r.proof.s.Design(r.proof.old.BUILD/"sim/simv.vdb")
    r.proof.require(single["design"]==before["design"],"Compiled design differs")
    for path,h in single["design"].items():read(design.db/path,h)
    sourceinfo=design.db/"auxiliary/verilog.sourceinfo.xml";read(sourceinfo)
    r.proof.require(design.source(r.SCOPE)["resolved_path"]==str(r.proof.ROOT/"hardware/src/ara_dispatcher.sv"),
                    "Source owner differs")
    definition=design.definition(r.SCOPE,"branch")
    current,previous=single["metrics"]["branch"][r.SCOPE],before["metrics"]["branch"][r.SCOPE]
    r.proof.require(current["checksum"]==previous["checksum"]==definition.get("chksum")=="1558979345"
                    and current["width"]==previous["width"]==1215,"Dispatcher branch shape differs")
    ps={p["raw_index"]:p for p in points("branch",definition,1215)}
    selectors=(
        (142,"25","987",1236,"1",True,"snapshot_entry_5720"),
        (141,"25","988",1242,"1",True,"reshuffle_entry_5751"),
        (158,"25","971",1218,"1",True,"widen_snapshot_gate_false_5642"),
        (159,"25","970",1217,"1",True,"widen_snapshot_gate_true_5642"),
        (76,"24","41",60,"1",True,"snapshot_capture_ready_1505"),
        (74,"24","43",63,"1",True,"snapshot_wait_complete_1512"),
        (96,"24","21",31,"0",False,"overlap_capture_not_ready_1364"),
        (97,"24","20",31,"1",False,"overlap_capture_ready_1364"),
        (127,"25","1002",1260,"1",False,"target_false_boundary_5843"))
    bindings=[]
    for raw,spec,vector,index,value,expected,label in selectors:
        point=ps[raw]
        r.proof.require((point["native_id"],point["vector"],point["file_id"])==(spec,vector,"547") and
                        expression_bit(point["native_vector"]["vector"],index)==value and
                        hit(current,raw)==expected,"Native bitmap route differs: "+label)
        bindings.append(dict(label=label,raw_index=raw,hit_single=expected,hit_before=hit(previous,raw),
            integer_bit=1214-raw,path_index_1_based_lsb=index,left_character_offset=len(point["native_vector"]["vector"])-index,
            path_character=value,point=point))
    rows=list(csv.DictReader(io.StringIO(read(RUN/"commit_trace.csv").decode())))
    vr=list(csv.DictReader(io.StringIO(read(RUN/"vector_trace.csv").decode())))
    events=[x for x in rows if x["event"]!="retire" and x["order"]=="43"]
    start=[x for x in events if x["event"]=="arch_start"]
    retire=[x for x in rows if x["event"]=="retire" and int(x["pc"],16)==0x8000222c and int(x["insn"],16)==r.proof.WORD]
    r.proof.require(len(start)==len(retire)==1 and start[0]["cycle"]=="14006" and retire[0]["cycle"]=="14066"
                    and retire[0]["order"]=="8609" and retire[0]["trap"]=="0","Architecture identity differs")
    allocations=[x for x in vr if x["arch_seq"]=="43" and x["event"]=="alloc"]
    dones=[x for x in vr if x["arch_seq"]=="43" and x["event"]=="done"]
    expected=((14008,14027,0,0,1,129),(14031,14046,1,8,2,32),
              (14048,14063,1,12,2,32),(14065,14090,1,8,2,129))
    r.proof.require(len(allocations)==len(dones)==4,"Not four complete uops")
    uops=[]
    for alloc,done,(ac,dc,use,vd,eew,vl) in zip(allocations,dones,expected):
        r.proof.require(tuple(int(alloc[k]) for k in ("cycle","use_vd","vd","eew","vl"))==(ac,use,vd,eew,vl)
                        and int(done["cycle"])==dc and all(alloc[k]==done[k] for k in
                        ("vid","insn","use_vd","vd","eew","vl","vstart")),"Actual uop fields differ")
        writes=[x for x in vr if x["arch_seq"]=="43" and x["event"]=="write" and ac<=int(x["cycle"])<=dc]
        uops.append(dict(alloc=alloc,done=done,granted_write_rows=len(writes),
                         granted_write_bytes=sum(bin(int(x["be"],16)).count("1") for x in writes)))
    r.proof.require([x["granted_write_bytes"] for x in uops]==[0,128,128,516],"Physical write population differs")
    read(Path(__file__).resolve());read(Path(__file__).with_name("test_explain_gap102_snapshot_path.py"))
    read(Path(expression_bit.__code__.co_filename).resolve())
    read(Path(bitmap.__file__).resolve())
    r.life.check(pins)
    return dict(status="GAP102_OBSERVED_SOURCE_SNAPSHOT_ROUTE_ZERO_INCREMENT_NOT_UNREACHABILITY_PROOF",
        baseline_tests=717,admitted=False,waiver_approved=False,rtl_changed=False,simulations_started=False,
        scope=r.SCOPE,source_hash=pins[str(source)],pins=pins,raw_delta=delta["metrics"],native_bindings=bindings,
        start=start[0],retire=retire[0],commit_events=events,uops=uops,
        inference="source capture then ordinary reshuffles then original MAC; resolves_widen excludes overlap repair",
        limitations=["No state_q, ara_req.op, source_snapshot_valid_q or replay/resolve probe in these CSVs.",
                     "insn is verify_arch_insn, not the internal maintenance operation opcode.",
                     "Native raw hit bits are whole software test accumulation, not per-cycle or per-seq43 attribution.",
                     "Neither zero gain nor this route proves global or configuration unreachability of raw127."],
        reachability_hold=dict(status="NOT_PROVEN_UNREACHABLE",possible_prestate_only=True,
            vstart=128,vl=129,destination_active=active_regs(8,2,128,129,8),
            narrow_source_active=active_regs(12,1,128,129,4),
            note="Disjoint active register metadata can avoid the snapshot conflict; legality/reachability not simulated."))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    out=parser.parse_args().output.absolute()
    r.proof.require(out.parent==OUT and out.resolve()==out and not out.exists(),"Fresh direct evidence required")
    result=explain();r.life.save(out,result)
    print(json.dumps(dict(output=str(out),seal=r.life.digest(out),status=result["status"])))


if __name__=="__main__":main()
