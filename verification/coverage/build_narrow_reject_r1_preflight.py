"""Independent R1 rejection matrix: host/Spike preflight and offline diff only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess

import build_opivx_vsbc_preflight as shared
import collect_opivx_vsbc_strict as strict
import review_rvv_reachable_719 as review

life, require = shared.life, shared.require
ROOT, OUT, LLVM, SPIKE = shared.ROOT, shared.OUT, shared.LLVM, shared.SPIKE
NAME = "vnarrow_reject_r1_matrix"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
REVIEW = OUT / "rvv-reachable-shortlist-719-20261006-01.json"
REVIEW_SEAL = "e71b5f1b348d9413dfaac82a86ee06ae621fa0a7a7db5d2dc9696189d40a0f76"
CHECKS = 15489
CASES = review.specifications()[0]["tests"]
SYMBOLS = ("tohost", "g75_result", "num_failed", "trap_fail", "gnr_ledger", "gnr_post",
           "gnr_restore", "gnr_traps", "gnr_dump", "gnr_recovery", "gnr_handler",
           "gnr_handler_end", "gnr_init_begin", "gnr_init_end") + tuple("gnr_bad_%02d" % n for n in range(24))
RECOVERY = 0x0283c857


def vtype(case):
    return ((3 if case["sew"] == 64 else 0) << 3) | {"m1": 0, "m2": 1, "m4": 2}[case["lmul"]]


def expected_register(reg, recovery=False):
    value = bytearray((reg * 29 + i * 13 + ((i >> 3) ^ reg) * 7 + 0x35) & 255 for i in range(128))
    if recovery and reg == 16:
        value[:4] = bytes((8 * 29 + i * 13 + ((i >> 3) ^ 8) * 7 + 0x36) & 255 for i in range(4))
    return bytes(value)


def verify_elf(blob, symbols):
    require(blob[:6] == b"\x7fELF\x02\x01", "Not ELF64 LE")
    h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(h[:3] == (2, 243, 1) and h[10] == 64 and h[5] + h[11] * 64 <= len(blob), "ELF header")
    pairs = [("gnr_bad_%02d" % n, int(c["word"],16)) for n,c in enumerate(CASES)] + [("gnr_recovery", RECOVERY)]
    require(len({symbols[n] for n,_ in pairs}) == 25, "Fault/recovery PCs alias")
    for name, word in pairs:
        pc, owners = symbols[name], []
        require(pc % 4 == 0, "Fault/recovery alignment")
        for i in range(h[11]):
            sec = struct.unpack_from("<IIQQQQIIQQ", blob, h[5] + i * 64)
            if sec[1] == 1 and sec[2] & 4 and sec[3] <= pc and pc + 4 <= sec[3] + sec[5]:
                owners.append(struct.unpack_from("<I",blob,sec[4]+pc-sec[3])[0])
        require(owners == [word], "Exact R1 ELF word differs: " + name)


def signatures(read, symbols):
    require(read("g75_result",width=4)==CHECKS and read("g75_result",4,4)==read("num_failed",width=4)==0,
            "Software result/check population differs")
    restore=[read("gnr_restore",i*8) for i in range(12)]
    require(all(restore[i]==restore[i+1] for i in range(0,12,2)) and restore[0]==symbols["trap_fail"] and
            restore[2]==0 and 0x80100000<=restore[4]<0x80200000 and restore[4]%16==0 and
            restore[6:]==[0]*6, "Context restoration differs")
    sp=restore[4]
    for n,case in enumerate(CASES):
        require([read("gnr_ledger",(n*12+i)*8) for i in range(12)]==
            [2,symbols["gnr_bad_%02d"%n],int(case["word"],16),4,vtype(case),1,5,n+1,0x2222,1,117,sp],
            "Trap ledger differs at case %d"%n)
        require([read("gnr_post",(n*9+i)*8) for i in range(9)]==
            [0x1111,0x2222,1,sp,1,4,vtype(case),5,117], "Post-mret preservation differs at case %d"%n)
    require(read("gnr_traps")==24, "Trap count differs")
    for phase in range(26):
        for reg in range(32):
            wanted=bytes([0xa5]*8)+expected_register(reg,phase==25)+bytes([0xa5]*8)
            actual=b"".join(read("gnr_dump",((phase*32+reg)*18+w)*8).to_bytes(8,"little") for w in range(18))
            require(actual==wanted, "Full VRF/guard differs phase=%d reg=%d"%(phase,reg))


def validate(commits,symbols,trace):
    events=re.findall(r"exception ([^,\n]+), epc (0x[0-9a-fA-F]+)",trace)
    pcs=[symbols["gnr_bad_%02d"%n] for n in range(24)]
    require([(n,int(pc,16)) for n,pc in events]==[("trap_illegal_instruction",pc) for pc in pcs] and
            trace.count("exception ")==24,"Not exact ordered24 illegal traps")
    require(not any(c.pc in (*pcs,symbols["trap_fail"]) for c in commits),"Fault retired/fatal handler")
    memory,terminal,vectors,stores={},[],[],[]
    handlers=[c for c in commits if symbols["gnr_handler"]<=c.pc<symbols["gnr_handler_end"]]
    require(sum(c.pc==symbols["gnr_handler"] for c in handlers)==24,"Handler entry count")
    for c in commits:
        handler=symbols["gnr_handler"]<=c.pc<symbols["gnr_handler_end"]
        for a,v in c.memory_accesses:
            if v is None:continue
            width=shared.store_width(c.instruction)
            require(0<=v<1<<(8*width),"Store width mismatch")
            for i in range(width):memory[a+i]=(v>>(8*i))&255
            if a==symbols["tohost"]:terminal.append(v)
            if handler:stores.append((a,width))
        for reg,value in c.vector_writes.items():vectors.append((c.pc,reg,value))
    def read(name,offset=0,width=8):
        addr=symbols[name]+offset
        require(all(addr+i in memory for i in range(width)),"Missing signature bytes")
        return int.from_bytes(bytes(memory[addr+i] for i in range(width)),"little")
    require(terminal==[1],"Terminal missing/repeated/nonPASS")
    signatures(read,symbols)
    allowed=Counter({(symbols["gnr_ledger"]+i*8,8):1 for i in range(24*12)})
    allowed[(symbols["gnr_traps"],8)]=24
    require(Counter(stores)==allowed,"Handler stores outside exact312-word footprint")
    require(all(not c.vector_writes and not c.fpr_writes and set(c.gpr_writes)<={5,6,7} and
                set(c.csr_writes)<={0x300,0x340,0x341} for c in handlers),"Protected handler state modified")
    require(Counter(r for _,r,_ in vectors)==Counter({r:(2 if r==16 else 1) for r in range(32)}),
            "Unexpected vector-write population")
    for reg in range(32):
        actual=[(pc,v) for pc,r,v in vectors if r==reg]
        require(symbols["gnr_init_begin"]<=actual[0][0]<symbols["gnr_init_end"],"Unexpected init PC")
        wanted=[int.from_bytes(expected_register(reg),"little")]
        if reg==16:
            wanted.append(int.from_bytes(expected_register(reg,True),"little"))
            require(actual[-1][0]==symbols["gnr_recovery"],"Recovery PC mismatch")
        require([v for _,v in actual]==wanted,"VRF write value differs")
    return dict(status="R1_HOST_SPIKE_FULL_ORACLE_PASS_NOT_DUT",checks=CHECKS,illegal_traps=24,
        ordered_fault_pcs=pcs,trap_vstart=1,post_mret_vstart=1,handler_store_words=312,
        observed_vrf_bytes=26*32*128,guard_bytes=26*32*16,vector_write_instructions=33,
        illegal_vector_writes=0,coverage_admitted=False)


def verify(out,seal):
    pre=life.read_bound(out/"preflight-manifest.json",seal)
    require(pre["status"]=="R1_REJECT_MATRIX_PREFLIGHT_PASS_NOT_VCS" and pre["case"]==NAME and
        pre["baseline_tests"]==719 and not pre["vcs_started"] and not pre["coverage_admitted"] and
        not pre["rtl_changed"],"Wrong R1 preflight contract")
    life.check(pre["pins"])
    symbols={n:shared._elf_symbol(out/"input.elf",LLVM/"llvm-readelf",n) for n in SYMBOLS}
    require(symbols==pre["symbols"],"Symbol drift")
    verify_elf((out/"input.elf").read_bytes(),symbols)
    commits=shared.parse_spike_commits(out/"spike.trace")
    require(validate(commits,symbols,(out/"spike.trace").read_text())==pre["validation"],"Oracle replay differs")
    require(strict.reference_counts(commits,symbols)==pre["reference_counts"],"Full scalar counts differ")
    return pre


def build(out):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),"Fresh R1 output required")
    report=life.read_bound(REVIEW,REVIEW_SEAL);life.check(report["pins"])
    require(report["baseline"]==719 and report["candidates"][0]["tests"] and
        [{k:t[k] for k in CASES[0]} for t in report["candidates"][0]["tests"]]==CASES,"R1 matrix drift")
    original=OUT/"opivx-vsbc-vd0-preflight-717-20261006-02"
    old=life.read_bound(original/"preflight-manifest.json","3b4e1c23901fe45c0b1e5434e7f244d2a8e041b103e0e0315cfd59ef685e3d09")
    template=original/"compile-command.json"
    command=life.read_bound(template,old["pins"][str(template)])
    require(command[0]==str(LLVM/"clang") and command.count(str(shared.APP))==1 and
        command.count(str(original/"input.elf"))==1,"Compile template mismatch")
    command=[str(APP) if x==str(shared.APP) else str(out/"input.elf") if x==str(original/"input.elf") else x for x in command]
    require(not any("Terapines" in x or "ZCC" in x for x in command),"Forbidden tool")
    paths=[APP,ROOT/"verification/tests/narrow_reject_r1_reference.h",ROOT/"verification/tests/narrow_reject_r1_host.c",
        ROOT/"verification/tests/gap75_start.S",ROOT/"verification/tests/gap75.ld",LLVM/"clang",LLVM/"ld.lld",LLVM/"llvm-readelf",
        SPIKE,Path('/usr/bin/cc').resolve(),Path(__file__).resolve(),Path(__file__).with_name("test_narrow_reject_r1_preflight.py"),
        Path(shared.__file__).resolve(),Path(strict.__file__).resolve(),Path(life.__file__).resolve(),
        ROOT/"verification/ara_verify/spike_trace.py",ROOT/"verification/ara_verify/vector_commit.py",
        ROOT/"verification/ara_verify/trace.py",ROOT/"verification/ara_verify/random_rvv.py",template,
        original/"preflight-manifest.json"]
    pins=life.merge_pins(report["pins"],{str(REVIEW):REVIEW_SEAL})
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in paths})
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image["image"])==66 and image["image"][str(life.IMAGE)]==
        "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3","Frozen simv66 mismatch")
    pins=life.merge_pins(pins,image["image"])
    pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL});life.check(pins)
    out.mkdir();life.save(out/"input-pins.json",pins)
    try:
        host=["/usr/bin/cc","-std=c11","-Wall","-Wextra","-Werror",str(ROOT/"verification/tests/narrow_reject_r1_host.c"),"-o",str(out/"host-reference")]
        life.save(out/"host-command.json",host)
        with (out/"host.log").open('x') as log:
            subprocess.run(host,check=True,timeout=60,stdout=log,stderr=subprocess.STDOUT)
            subprocess.run([str(out/"host-reference")],check=True,timeout=10,stdout=log,stderr=subprocess.STDOUT)
        fnv=14695981039346656037
        for r in range(32):
            for v in expected_register(r):fnv=((fnv^v)*1099511628211)&((1<<64)-1)
        require((out/"host.log").read_text()=="R1_HOST_PASS cases=24 checks=15489 seed_fnv=%016x\n"%fnv,"Host independent seed oracle")
        life.save(out/"compile-command.json",command)
        with (out/"compile.log").open('x') as log:subprocess.run(command,check=True,timeout=120,stdout=log,stderr=subprocess.STDOUT)
        symbols={n:shared._elf_symbol(out/"input.elf",LLVM/"llvm-readelf",n) for n in SYMBOLS}
        verify_elf((out/"input.elf").read_bytes(),symbols)
        baselinepins=json.loads((review.BASE/"evidence-pins.json").read_text());h=life.digest(out/"input.elf")
        require(not any(p.endswith('.elf') and v==h for p,v in baselinepins.items()),"Duplicate baseline ELF")
        life.save(out/"elf-dedup.json",dict(baseline=719,input_elf_sha256=h,
            checked_baseline_elf_pins=sum(p.endswith('.elf') for p in baselinepins),duplicate_elf=False,
            baseline_pin_manifest_sha256=life.digest(review.BASE/"evidence-pins.json"),new_case_not_admitted=True))
        spike=[str(SPIKE),"--isa=rv64gcv_zfh_zvfh_zvl1024b","--priv=msu","--pmpregions=0","-l","--log-commits",str(out/"input.elf")]
        life.save(out/"spike-command.json",spike)
        with (out/"spike.stdout").open('x') as stdout,(out/"spike.trace").open('x') as trace:
            subprocess.run(spike,check=True,timeout=180,stdout=stdout,stderr=trace)
        commits=shared.parse_spike_commits(out/"spike.trace")
        result=validate(commits,symbols,(out/"spike.trace").read_text())
        counts=strict.reference_counts(commits,symbols)
        life.save(out/"spike-validation.json",result);life.save(out/"target-before.json",report["candidates"][0]["zero_targets"])
        life.check(pins)
        pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
        pre=dict(status="R1_REJECT_MATRIX_PREFLIGHT_PASS_NOT_VCS",case=NAME,baseline_tests=719,
            input_elf=str(out/"input.elf"),pins=pins,symbols=symbols,validation=result,reference_counts=counts,
            targets=report["candidates"][0]["zero_targets"],coverage_admitted=False,vcs_started=False,rtl_changed=False,
            measured_raw_increment=None,old_image_files_checked=66,ZCC_executed=False,
            separate_from_descartes_positive_narrow_prefix=True,
            full_scalar_vector_diff_entry="build_narrow_reject_r1_preflight.py compare --output PREFLIGHT --seal SEAL --dut EXISTING_DUT_DIRECTORY --comparison NEW_JSON",
            dut_diff_executed=False)
        life.save(out/"preflight-manifest.json",pre)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/"preflight-manifest.json"),validation=result,elf_sha256=h)))
    except Exception as error:
        life.save(out/"failure.json",dict(status="R1_PREFLIGHT_FAILED_NO_VCS",reason=str(error)));raise


def compare(out,seal,dut,result_path):
    pre=verify(out,seal)
    require(result_path and not result_path.exists(),"Fresh comparison JSON required")
    scalar=strict.spike_trace.compare_commit_prefix(out/"spike.trace",dut/"commit_trace.csv",0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout="unshifted")
    strict.scalar_exact(scalar,pre["reference_counts"])
    vector=strict.compare_vector_commits(out/"spike.trace",dut/"commit_trace.csv",dut/"vector_trace.csv",0x80000000)
    for k,v in dict(status="PASS",compared_instructions=33,vector_destination_requests=33,
        skipped_unknown_bytes=0,non_bit_exact_instructions=0,unobservable_instructions=0,
        incomplete_requests=[],unretired_requests=[],first_mismatch=None).items():
        require(vector.get(k)==v,"Incomplete vector comparison: "+k)
    require(len(vector['instructions'])==33 and all(x['status']=='PASS' and x['compared_bytes']==128
        for x in vector['instructions'][:32]) and 4<=vector['instructions'][-1]['compared_bytes']<=128,
        "Not full initialized VRF + legal recovery")
    require(len(vector['trapped_requests'])==24 and len(set(vector['trapped_requests']))==24,"Illegal request count")
    life.save(result_path,dict(status="FULL_SCALAR_VECTOR_DIFF_PASS_NOT_ADMISSION",scalar=scalar,vector=vector,
        preflight_seal=seal,input_pins={str(dut/n):life.digest(dut/n) for n in ('commit_trace.csv','vector_trace.csv')},
        coverage_admitted=False))
    print("FULL_DIFF_PASS_NOT_ADMISSION")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('build','verify','compare'))
    p.add_argument('--output',required=True,type=Path);p.add_argument('--seal');p.add_argument('--dut',type=Path)
    p.add_argument('--comparison',type=Path);a=p.parse_args()
    require((a.mode!='build')==bool(a.seal),'Only replay/compare require seal')
    if a.mode=='build':build(a.output.absolute())
    elif a.mode=='verify':verify(a.output.absolute(),a.seal);print('VERIFY_PASS ordered24/full32VRF/CSR/guard/host/Spike NO_VCS admitted0')
    else:
        require(a.dut is not None,'DUT existing trace directory required')
        compare(a.output.absolute(),a.seal,a.dut.absolute(),a.comparison)


if __name__=='__main__':main()
