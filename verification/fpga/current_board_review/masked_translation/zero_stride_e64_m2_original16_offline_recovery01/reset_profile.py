"""M7 XLEN64 image-bound startup mstatus only; no unknown-CSR default."""
from pathlib import Path
import checker as c
SNAP=Path('/home/wangwy/fpga_runs/current_board_memory_candidate07/frozen/sources')
FILES=[
 'hardware/deps/cva6/core/csr_regfile.sv',
 'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
 'hardware/deps/cva6/core/include/build_config_pkg.sv']
RESET_MSTATUS=(2<<32)|(2<<34)
def initial_csrs():
    plan=c.read(c.HERE/'prepared01/plan.json')
    c.require(plan['image']==str(c.IMAGE),'M7-specific reset profile')
    for f in FILES:
        p=SNAP/f
        c.require(plan['pins'].get(str(p))==c.sha(p),'Frozen reset/config source pin '+f)
    cfg=(SNAP/FILES[1]).read_text();rtl=(SNAP/FILES[0]).read_text()
    c.require('CVA6ConfigXlen = 64;' in cfg and 'CVA6ConfigVExtEn = 1;' in cfg and 'CVA6ConfigRVF = 1;' in cfg,'Actual M7 XLEN64/F/V')
    for s in ("mstatus_q        <= 64'b0;","mstatus_d.sxl = riscv::XLEN_64;","mstatus_d.uxl = riscv::XLEN_64;","mstatus_d.xs = riscv::Off;"):
        c.require(s in rtl,'Reset/write source missing '+s)
    return {0x300:RESET_MSTATUS}
def sd(v):
    return int(any(((v>>shift)&3)==3 for shift in (9,13,15)))
def mstatus_warl(v):
    # This fixture uses only legal writable fields; XS is hardwired Off and SD derived.
    v=(v&~((15<<32)|(3<<15)|(1<<63)))|RESET_MSTATUS
    return v|(sd(v)<<63)
def check_mstatus_read(v):
    c.require(v&(15<<32)==RESET_MSTATUS,'Actual mstatus fixed UXL/SXL')
    c.require((v>>63)==sd(v),'Actual mstatus SD/FS/VS/XS Dirty derivation')

