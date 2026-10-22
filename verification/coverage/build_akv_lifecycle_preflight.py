"""Formal721-bound AKV lifecycle software preflight; never starts RTL simulation."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

import build_akv_column_boundary_v2_preflight as reuse
import closure_point_inventory as shape
from inventory_operand_debug import Design

shared=reuse.shared
ROOT,OUT,sha,save,require=shared.ROOT,shared.OUT,shared.sha,shared.save,shared.require
BASE=OUT/"akv-column-boundary-offline-admitted-721-20261006-01"
BASE_SEAL="eda7720583e3232e97cd4486d7790a678abc108018f6acbd56d0b1c287e20c8b"
BUILD=reuse.BUILD
NAME="vakv_lifecycle_boundary"
APP=ROOT/"apps/riscv-tests/isa/rv64uv"/(NAME+".c")
SCOPE=reuse.SCOPE
WORDS=[0x0000505b,0x02a0605b,0x00b5605b,0x02a0205b,0x00b5205b,
       0x0405345b,0x02a0205b,0x00b5205b,0x0005345b,0x0000505b]
BAD_PHASES=(1,3,5,6)
ERRORS=[12,12,6,11]
FAULTS=[int(i in BAD_PHASES) for i in range(10)]
SOFTWARE_CHECKS,DUT_CHECKS=7735,7740
FRAME_BYTES=4224


def expected_frame(phase):
    require(type(phase) is int and 0<=phase<10,"Wrong phase")
    before=struct.pack("<8Q",*[0xc100+phase*16+i for i in range(8)])
    data=struct.pack("<2048H",*[0x2400+i if phase>=8 and r==8 else 0x1000+r*64+i
                              for r in range(32) for i in range(64)])
    after=struct.pack("<8Q",*[0xc200+phase*16+i for i in range(8)])
    return before+data+after


def expected_seed():
    return struct.pack("<8Q",*[0xa100+i for i in range(8)])+expected_frame(0)[64:-64]+\
        struct.pack("<8Q",*[0xa200+i for i in range(8)])


def expected_sources():
    return b"".join(struct.pack("<8Q",*[0xb100+s*16+i for i in range(8)])+
                    struct.pack("<64H",*[0x2400+s*0x1000+i for i in range(64)])+
                    struct.pack("<8Q",*[0xb200+s*16+i for i in range(8)]) for s in range(3))


def reference_lifecycle(operations=None):
    # Independent bounded lifecycle predicates; no observed DUT values enter here.
    operations=operations or [("release",), ("refill",True,0), ("full",True),
        ("refill",False,0), ("full",False), ("row",96), ("refill",False,1),
        ("full",False), ("row",64), ("release",)]
    ready=False;v2=False;errors=[];ready_after=[]
    for op in operations:
        error=0
        if op[0]=="release":ready=False;v2=False
        elif op[0]=="full":ready=True;v2=op[1]
        elif op[0]=="refill":
            if not ready or op[1]!=v2:error=12
            elif op[2]>=1:error=11
            else:raise ValueError("Successful refill outside bounded oracle")
            ready=False
        elif op[0]=="row":
            if not ready:error=12
            elif not (op[1] in (64,128) or (v2 and op[1]==96)) or op[1]!=64:error=6
        else:raise ValueError("Unknown reference operation")
        errors.append(error);ready_after.append(ready)
    return dict(validation_errors=errors,context_ready_after=ready_after,
                custom_write_bytes=[0]*8+[128,0])


def native_elf_audit(blob,symbols):
    require(blob[:6]==b"\x7fELF\x02\x01","Expected ELF64 little endian")
    h=struct.unpack_from("<HHIQQQIHHHHHH",blob,16)
    require(h[0]==2 and h[1]==243 and h[8]==56 and not h[6]&1,"Wrong ELF/noC ABI")
    found={}
    for i in range(h[9]):
        kind,flags,off,address,_,size,total,_=struct.unpack_from("<IIQQQQQQ",blob,h[4]+56*i)
        if kind!=1:continue
        require(size<=total and off+size<=len(blob) and 0x80000000<=address<=address+total<=0x80200000,
                "Bad ELF segment")
        if flags&1:
            require(address%4==size%4==0,"Compressed executable")
            for n in range(0,size,4):
                word=int.from_bytes(blob[off+n:off+n+4],"little")
                if word&127==0x5b:found[address+n]=word
    expected={symbols["lifecycle_site_"+str(i)]:word for i,word in enumerate(WORDS)}
    require(len(expected)==10 and found==expected,"Missing/extra/incorrect native command site")
    return dict(status="EXACT_TEN_NATIVE_SITES_STATIC_NOT_EXECUTED",sites=[dict(phase=i,
        pc=symbols["lifecycle_site_"+str(i)],word=w,expected_exception=i in BAD_PHASES)
        for i,w in enumerate(WORDS)],custom_execution=False)


def target_evidence():
    pins={str(BASE/"admission-manifest.json"):BASE_SEAL}
    require(sha(BASE/"admission-manifest.json")==BASE_SEAL,"Wrong formal721 seal")
    manifest=json.loads((BASE/"admission-manifest.json").read_text())
    require(manifest["schema"]=="AKV_INDEPENDENT_SCALAR_HISTORICAL721_ADMISSION_V1" and
            manifest["output"]==str(BASE),"Wrong formal721 identity")
    pins.update(manifest["output_pins"])
    shared.check(pins)
    bitmap=json.loads((BASE/"combined-bits.json").read_text())
    status=json.loads((BASE/"status.json").read_text())
    require(status["status"]=="PASS_RAW_UNION_HISTORICAL_ONLY" and
            type(status["aggregate_passed"]) is int and status["aggregate_passed"]==721 and
            len(bitmap["tests"])==len(set(bitmap["tests"]))==721,"Wrong721 PASS population")
    design_path=BUILD/"sim/simv.vdb"
    require((BASE/"combined-inputs.txt").read_text().splitlines()==[str(design_path),*bitmap["tests"]],
            "Wrong721 ordered ledger")
    source_manifest=BUILD/"build-source-pins.json";pins[str(source_manifest)]=sha(source_manifest)
    sources=json.loads(source_manifest.read_text())
    for rel in ("hardware/src/vlsu/akv/akv_engine.sv","hardware/src/vlsu/akv/akv_context.sv",
                "hardware/src/vlsu/akv/akv_v2_context.sv","hardware/src/vlsu/vlsu.sv","hardware/include/akv_pkg.sv",
                "hardware/src/ara_soc.sv","hardware/src/ara_system.sv"):
        p=ROOT/rel;require(sha(p)==sources[str(p)],"Frozen source drift: "+rel);pins[str(p)]=sources[str(p)]
    dispatcher=OUT/"old-image-source-evidence-20261006-01/ara_dispatcher.sv"
    require(sha(dispatcher)==sources[str(ROOT/"hardware/src/ara_dispatcher.sv")],"Wrong frozen dispatcher")
    pins[str(dispatcher)]=sha(dispatcher)
    design=Design(design_path)
    for relative,hash_value in bitmap["design"].items():pins[str(design.db/relative)]=hash_value
    for relative in ("auxiliary/verilog.sourceinfo.xml","shape/cond.verilog.shape.xml","shape/cond.verilog.info.xml"):
        p=design.db/relative;pins[str(p)]=sha(p)
    record=bitmap["metrics"]["cond"][SCOPE]
    require(record["width"]==392 and record["checksum"]=="2836473276" and
            design.hierarchy[SCOPE].get("chksum")=="3509320291","AKV compiled identity drift")
    cond=shape.read_xml(design.db/"shape/cond.verilog.shape.xml")
    mapped={p["raw_index"]:p for p in shape.points("cond",shape.definition(cond,design.hierarchy[SCOPE],record["checksum"]),392)}
    coordinates={8:("4","305","01"),194:("78","947","1"),199:("80","953","0"),201:("81","958","0")}
    targets=[]
    for raw,(identifier,line,vector) in coordinates.items():
        p=mapped[raw]
        require((p["native_id"],p["line"],p["vector"])==(identifier,line,vector) and
                not int(record["bits"],16)>>(391-raw)&1,"Compiled target not exact721 zero")
        targets.append(dict(scope=SCOPE,metric="cond",raw_index=raw,bitmap_LSB_index=391-raw,
            width=392,checksum=record["checksum"],point=p,baseline_hit=False,native_GUI_ID_qualification=False))
    shared.check(pins)
    return pins,dict(baseline_tests=721,baseline_seal=BASE_SEAL,design=str(design_path),
        module_checksum="3509320291",source=design.source(SCOPE),targets=targets,
        expected_increment_not_measured=True,exclusions_generated=False)


def validate_software(commits,symbols):
    require(commits and not any(c.vector_writes or c.pc==symbols["trap_fail"] for c in commits),
            "Unexpected real software trap/vector data write")
    data=reuse.memory(commits)
    def read(name,size):
        start=symbols[name]
        require(all(start+i in data for i in range(size)),"Missing observed software bytes: "+name)
        return bytes(data[start+i] for i in range(size))
    require(read("tohost",8)==struct.pack("<Q",1) and
            read("g75_result",8)==struct.pack("<2I",SOFTWARE_CHECKS,0) and
            read("num_failed",4)==bytes(4),"Software signature differs")
    require(read("lifecycle_snapshots",10*FRAME_BYTES)==b"".join(expected_frame(p) for p in range(10)),
            "Incomplete/wrong complete VRF frames or guards")
    require(read("lifecycle_seed",FRAME_BYTES)==expected_seed() and
            read("lifecycle_sources",768)==expected_sources(),"Changed input/seed/guard bytes")
    source=symbols["lifecycle_sources"]
    descriptor=struct.pack("<4B2H4I5Q",1,1,1,0,64,1,128,128,128,0,
                           source+64,source+256+64,source+512+64,0,0)
    require(read("lifecycle_descriptor",64)==descriptor,"Changed descriptor fields/addresses")
    require(read("lifecycle_csrs",480)==struct.pack("<60Q",*([21,0,64,8,2,1]*10)),"Actual CSR snapshots differ")
    require(read("lifecycle_status",40)==struct.pack("<10I",*FAULTS),"Wrong rejection sequence")
    require(read("lifecycle_scan",80)==struct.pack("<20I",*([512,0]*10)),"Incomplete full-frame comparison")
    require(read("lifecycle_trap_count",8)==struct.pack("<Q",4) and
            read("lifecycle_semantic_errors",16)==struct.pack("<4I",*ERRORS),"Wrong software semantic ledger")
    require(read("g75_trap",24)==bytes(24),"Actual unexpected software trap")
    terminal=[v for c in commits for address,v in c.memory_accesses if address==symbols["tohost"] and v is not None]
    require(terminal==[1],"Nonunique software terminal")
    return dict(status="HOST_SPIKE_SOFTWARE_REFERENCE_PASS_NOT_NATIVE_CUSTOM",checks=SOFTWARE_CHECKS,
        full_VRF_frames=10,snapshot_data_bytes=40960,snapshot_guard_bytes=1280,
        actual_CSR_snapshot_bytes=480,semantic_rejections=4,real_Spike_traps=0,
        native_custom_executed=False,native_expected_write_bytes=128,coverage_increment_measured=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output.absolute()
    require(out.parent==OUT and out.resolve()==out and not out.exists(),"Fresh direct output required")
    pins,target=target_evidence()
    paths=[APP,reuse.REFERENCE,ROOT/"apps/common/string.c",Path(__file__).resolve(),
        Path(__file__).with_name("test_build_akv_lifecycle_preflight.py"),ROOT/"verification/tests/gap75_start.S",
        ROOT/"verification/tests/gap75.ld",shared.LLVM/"clang",shared.LLVM/"ld.lld",shared.LLVM/"llvm-readelf",
        shared.LLVM/"llvm-objdump",shared.SPIKE,Path("/usr/bin/cc").resolve(),ROOT/"apps/common/akv_abi.h",
        Path(reuse.__file__).resolve(),Path(reuse.original.__file__).resolve(),Path(shared.__file__).resolve(),
        Path(shape.__file__).resolve(),ROOT/"verification/coverage/inventory_operand_debug.py"]
    paths+=list((ROOT/"software/akv/include").rglob("*.h"))+list((ROOT/"verification/ara_verify").glob("*.py"))
    paths+=[reuse.SPIKE_SOURCE/"riscv/processor.cc",reuse.SPIKE_SOURCE/"riscv/riscv.mk.in",
            ROOT/"verification/coverage/build_gap95_preflight.py",ROOT/"verification/coverage/run_gap75_operand_batch.py"]
    for p in paths:pins[str(p)]=sha(p)
    shared.check(pins);out.mkdir();save(out/"target-before.json",target)
    def run(command,name,timeout=120):
        command=[str(c) for c in command];save(out/(name+"-command.json"),command)
        with (out/(name+".stdout")).open("x") as stdout,(out/(name+".stderr")).open("x") as stderr:
            subprocess.run(command,stdout=stdout,stderr=stderr,timeout=timeout,check=True)
    includes=["-I"+str(ROOT/"apps/common"),"-I"+str(ROOT/"software/akv/include")]
    names=("tohost","g75_result","num_failed","g75_trap","trap_fail","lifecycle_seed",
        "lifecycle_sources","lifecycle_descriptor","lifecycle_snapshots","lifecycle_csrs","lifecycle_status",
        "lifecycle_scan","lifecycle_trap_count","lifecycle_traps","lifecycle_semantic_errors","lifecycle_expected_pc")
    try:
        run(["/usr/bin/cc","-O2","-fno-tree-vectorize","-DAKV_LIFECYCLE_SOFTWARE","-DAKV_LIFECYCLE_HOST",
             *includes,APP,reuse.REFERENCE,"-o",out/"host"],"host-compile")
        run([out/"host"],"host",30)
        require((out/"host.stdout").read_text()=="AKV_LIFECYCLE_SOFTWARE checks=7735 errors=0\n","Host oracle failed")
        flags=["--target=riscv64-unknown-elf","-march=rv64gv_zfh_zvfh","-mabi=lp64d","-mcmodel=medany",
            "-mno-relax","-msmall-data-limit=0","-O2","-fno-vectorize","-fno-slp-vectorize","-ffreestanding",
            "-fno-builtin","-mno-implicit-float","-fuse-ld=lld","-nostdlib",*includes,
            "-T"+str(ROOT/"verification/tests/gap75.ld"),ROOT/"verification/tests/gap75_start.S"]
        run([shared.LLVM/"clang",*flags,APP,ROOT/"apps/common/string.c","-o",out/"input.elf"],"native-compile")
        run([shared.LLVM/"clang",*flags,"-march=rv64gv_zfh","-DAKV_LIFECYCLE_SOFTWARE",APP,
             reuse.REFERENCE,ROOT/"apps/common/string.c","-o",out/"software.elf"],"software-compile")
        software_symbols={n:shared._elf_symbol(out/"software.elf",shared.LLVM/"llvm-readelf",n) for n in names}
        native_symbols={n:shared._elf_symbol(out/"input.elf",shared.LLVM/"llvm-readelf",n)
                        for n in (*names,"lifecycle_handler",*("lifecycle_site_"+str(i) for i in range(10)))}
        native_audit=native_elf_audit((out/"input.elf").read_bytes(),native_symbols)
        save(out/"native-elf-audit.json",native_audit)
        save(out/"independent-lifecycle-oracle.json",reference_lifecycle())
        run([shared.LLVM/"llvm-objdump","-d",out/"input.elf"],"native-disassembly")
        run([shared.SPIKE,"--isa=rv64gcv_zfh_zvfh_zvl1024b","--priv=msu","--pmpregions=0","-l",
             "--log-commits",out/"software.elf"],"spike",180)
        validation=validate_software(shared.parse_spike_commits(out/"spike.stderr"),software_symbols)
        save(out/"spike-validation.json",validation);shared.check(pins)
        for p in out.iterdir():pins[str(p)]=sha(p)
        shared.check(pins)
        manifest=dict(status="AKV_LIFECYCLE_721_SOFTWARE_PREFLIGHT_PASS_NOT_VCS",case=NAME,baseline_tests=721,
            baseline_seal=BASE_SEAL,input_elf=str(out/"input.elf"),software_elf=str(out/"software.elf"),pins=pins,
            symbols=native_symbols,software_symbols=software_symbols,validation=validation,dut_checks=DUT_CHECKS,
            dut_expected_commands=10,dut_expected_traps=[dict(phase=i,pc=native_symbols["lifecycle_site_"+str(i)],
                cause=2,tval=0,validation_error=error) for i,error in zip(BAD_PHASES,ERRORS)],
            native_expected_custom_write_bytes=128,dut_expected_vrf_frames=10,dut_expected_CSR_bytes=480,
            full_scalar_differential_qualified=False,full_scalar_independent_qualified=False,
            software_reference_scope="V2 library FULL/release plus independently bounded V1 D64 lifecycle model; not native Spike custom",
            old_image_budget_s=300,source_ISA="rv64gv_zfh_zvfh",target_before=str(out/"target-before.json"),
            coverage_admitted=False,vcs_launched=False,rtl_changed=False,
            required_native_gates="full scalar independent qualification; exact10 commands/4 traps/128 bytes; all10 VRF frames/CSR/guards; D64 recovery")
        save(out/"preflight-manifest.json",manifest)
        print(json.dumps(dict(output=str(out),seal=sha(out/"preflight-manifest.json"),validation=validation)))
    except Exception as error:
        save(out/"failure.json",dict(status="AKV_LIFECYCLE_PREFLIGHT_FAILED",reason=str(error)))
        raise


if __name__=="__main__":main()
