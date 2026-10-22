"""Exact frozen M9 unsigned VSLIDEUP.VI eligibility, not a data waiver."""
from pathlib import Path
DISPATCHER=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/hardware/src/ara_dispatcher.sv')
DISPATCHER_SHA='c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d'
def no_work_reason(insn,vl,vstart):
    if not (type(insn)is int and type(vl)is int and type(vstart)is int and
        0<=insn<1<<32 and 0<=vl<=512 and 0<=vstart<=512):raise ValueError('Actual source dimensions required')
    if vstart>=vl:return 'vstart_ge_vl'
    if insn&127==0x57 and (insn>>12)&7==3 and insn>>26==0b001110:
        offset=(insn>>15)&31
        if offset>=vl:return 'unsigned_vslideup_vi_offset_ge_vl'
    return None
def required_target(insn,vl,vstart):return no_work_reason(insn,vl,vstart)is None
