"""Bound static single-register-store nonmutation proof; no new execution."""
import argparse
from collections import Counter
import json
from pathlib import Path

import build_gap103_preflight_v2 as pre

s, ROOT, OUT, require = pre.s, pre.ROOT, pre.OUT, pre.require
PRE = OUT / "gap103-narrow-prefix-preflight-719-20261006-02"
SEAL = "033ca91cb0e62dcf04655af186e8cf1a441c236d0d95bcf9d801f7a25cf5ddf4"


def source_contract(dispatcher, sequencer, vstu):
    def region(text,start,end):
        require(text.count(start) == 1,"Ambiguous source boundary")
        suffix = text.split(start,1)[1]
        require(suffix.count(end) == 1,"Ambiguous source end after selected start")
        return suffix.split(end,1)[0]
    whole = region(dispatcher,"// Vector whole register stores are encoded as stores of length VLENB",
                   "// Wait until the back-end answers to acknowledge those instructions")
    require("3'd0: begin" in whole and "ara_req.vl = VLENB << 0;" in whole and
            "ara_req.emul = LMUL_1;" in whole and "ara_req.vtype.vsew = EW8;" in whole,
            "Single whole-store decode differs")
    require("same_eew_by_lmul[LMUL_1] = 1'b1;" in dispatcher and
            "is_same_eew = same_eew_by_lmul[ara_req.emul[1:0]] | ara_req.emul[2];" in dispatcher,
            "Single-register uniform-layout predicate differs")
    require("(in_lane_op ||\n             (is_vstore && (is_segment_mem_op ||\n"+
            "                            (csr_vstart_q != '0) || !is_same_eew)))" in dispatcher,
            "Store source reshuffle gate differs")
    require("if (ara_req_valid_d && ara_req_d.use_vd && ara_req_ready_i &&" in dispatcher and
            "eew_d[layout_req.vd + i]       = layout_req.vtype.vsew;" in dispatcher,
            "Notebook destination-write gate differs")
    require("ara_req.old_eew_vs1 =" in dispatcher and
            "eew_q[ara_req.vs1 + first_active_register];" in dispatcher and
            "old_eew_vs1   : ara_req_i.old_eew_vs1," in sequencer and
            "shuffle_index(vrf_seq_byte, NrLanes, vinsn_issue_q.old_eew_vs1)" in vstu,
            "Old-layout store byte extraction chain differs")
    require("is_whole_reg" not in dispatcher,"Unexpected newer whole-register flag")
    return dict(snapshot_kind="32 independent vs1r.v, not multi-register vs8r.v",
        snapshot_emul=1,snapshot_vstart=0,segment=False,in_lane=False,is_same_eew=True,
        store_source="vs1/old_eew_vs1; use_vs2=false",use_vd=False,
        source_reshuffle_gate=False,destination_notebook_update=False,
        lower_v8_v11_eew=32,upper_v12_v15_eew=16,
        extraction="VSTU old_eew_vs1 shuffle mapping, does not rewrite VRF",
        static_not_direct_EEW_probe=True)


def evaluate():
    require(s.sha(PRE/"preflight-manifest.json") == SEAL,"Frozen preflight seal differs")
    manifest = json.loads((PRE/"preflight-manifest.json").read_bytes())
    pins = s.merge_pins(manifest["pins"],{str(PRE/"preflight-manifest.json"):SEAL})
    sources = json.loads((pre.old.BUILD/"build-source-pins.json").read_bytes())
    dispatcher = OUT/"old-image-source-evidence-20261006-01/ara_dispatcher.sv"
    sequencer = ROOT/"hardware/src/ara_sequencer.sv"
    vstu = ROOT/"hardware/src/vlsu/vstu.sv"
    for path,original in ((dispatcher,ROOT/"hardware/src/ara_dispatcher.sv"),(sequencer,sequencer),(vstu,vstu)):
        require(s.sha(path) == sources[str(original)],"Old build source pin differs")
        pins = s.merge_pins(pins,{str(path):sources[str(original)]})
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_prove_gap103_snapshot_scope.py")):
        pins = s.merge_pins(pins,{str(path):s.sha(path)})
    s.check(pins)
    result = source_contract(dispatcher.read_text(),sequencer.read_text(),vstu.read_text())
    commits = s.parse_spike_commits(Path(manifest["input_spike_trace"]))
    require(pre.validate(commits,manifest["symbols"],Path(manifest["input_spike_trace"]).read_text()) ==
            manifest["validation"],"Canonical preflight replay differs")
    low, high = manifest["symbols"]["g103_load_shift"],manifest["symbols"]["g103_narrow"]
    before_stores = [c for c in commits if low < c.pc < high and c.instruction & 0x7f == 0x27]
    require(len(before_stores) == 32 and
            Counter((c.instruction>>7)&31 for c in before_stores) == Counter(range(32)) and
            all(c.instruction & (0xffffffff ^ ((31<<15)|(31<<7))) == 0x02800027 and
                c.vector_vstart == 0 for c in before_stores),"Actual before-snapshot store contract differs")
    data = pre.images()
    require(data["before"][1536:2048] == data["shifts"][16:-16],"High half is not loaded shifts")
    wide = int.from_bytes(data["before"][1536:1540],"little")
    shift = int.from_bytes(data["before"][1792:1794],"little")&31
    expected = (wide>>shift)&65535
    require(int.from_bytes(data["after"][1280:1282],"little") == expected,"Canonical alias result differs")
    s.check(pins)
    return dict(status="GAP103_SINGLE_REGISTER_SNAPSHOT_STATIC_NONMUTATION_NOT_DUT_PROBE",
        pins=pins,preflight=str(PRE),preflight_seal=SEAL,source_contract=result,
        before_snapshot_store_instructions=32,
        aliased_wide_element128=wide,shift_element128_low5=shift,result_element128=expected,
        target_assumptions_preserved=True,coverage_admitted=False,vcs_started=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    output=parser.parse_args().output.absolute()
    require(output.parent == OUT and output.resolve() == output and not output.exists(),"Fresh proof output required")
    result=evaluate(); s.save(output,result)
    print(json.dumps(dict(output=str(output),seal=s.sha(output),pins=len(result["pins"]))))


if __name__ == "__main__": main()
