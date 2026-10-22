"""Bounded independent RV64 interpreter for the sealed AKV column v2 ELF only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import time

import check_akv_column_boundary_v5_offline as native

life, require = native.life, native.require
MASK = (1 << 64)-1
ELF_SHA = "400981058a5fb666bf651ca0dc32fe8b5582e1b0401a8f2c96a2c62801e0603d"
CANDIDATE = life.OUT / "akv-column-boundary-v5-native-candidate-20261006-01"
CANDIDATE_SHA = "0cb09bfa36605257f09ef3ff3a81e2c1e723973322039298722bc5804d06349e"
GPR_SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands.gen_asic_regfile.i_ariane_regfile"


def source_anchors(text,anchors):
    clean=re.sub(r"//[^\n]*|/\*.*?\*/","",text,flags=re.S)
    compact="".join(clean.split())
    for anchor in anchors:
        require("".join(anchor.split()) in compact,"Missing source contract anchor: "+anchor)


def source_contract(sources,pins):
    from inventory_operand_debug import Design
    files={
        "hardware/deps/cva6/core/ariane_regfile_ff.sv": ["if (~rst_ni) begin mem <= '{default: '0};", "if (ZERO_REG_ZERO) begin mem[0] <= '0;"],
        "hardware/deps/cva6/core/issue_read_operands.sv": ["if (CVA6Cfg.FpgaEn) begin : gen_fpga_regfile", "end else begin : gen_asic_regfile", ".ZERO_REG_ZERO(1)"],
        "hardware/deps/cva6/core/csr_regfile.sv": [
            "priv_lvl_q <= riscv::PRIV_LVL_M;", "mstatus_q <= 64'b0;", "fcsr_q <= '0;",
            "mepc_q <= {CVA6Cfg.XLEN{1'b0}};", "mcause_q <= {CVA6Cfg.XLEN{1'b0}};",
            "if (CVA6Cfg.TvalEn) mtval_q <= {CVA6Cfg.XLEN{1'b0}};",
            "if (CVA6Cfg.IS_XLEN64) begin mstatus_d.sxl = riscv::XLEN_64; mstatus_d.uxl = riscv::XLEN_64; end",
            "mtvec_d = {{CVA6Cfg.XLEN - CVA6Cfg.VLEN{1'b0}}, boot_addr_i} + 'h40;",
            "if (CVA6Cfg.FpPresent && (dirty_fp_state_csr || dirty_fp_state_i)) begin mstatus_d.fs = riscv::Dirty;",
            "if (CVA6Cfg.RVV && dirty_v_state_i) begin mstatus_d.vs = riscv::Dirty;",
            "mstatus_d.sd = (mstatus_d.xs == riscv::Dirty) | (mstatus_d.fs == riscv::Dirty) | (mstatus_d.vs == riscv::Dirty);",
            "mstatus_d.mie = 1'b0; mstatus_d.mpie = mstatus_q.mie;",
            "mstatus_d.mpp = priv_lvl_q;", "mstatus_d.mie = mstatus_q.mpie;",
            "priv_lvl_d = mstatus_q.mpp;", "if (CVA6Cfg.RVU) begin mstatus_d.mpp = riscv::PRIV_LVL_U;", "mstatus_d.mpie = 1'b1;"],
        "hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv": [
            "localparam CVA6ConfigXlen = 64;", "localparam CVA6ConfigHExtEn = 0;",
            "localparam CVA6ConfigVExtEn = 1;", "localparam CVA6ConfigSclicExtEn = 0;",
            "localparam CVA6ConfigTvalEn = 1;", "FpgaEn: bit'(0)",
            "XLEN: unsigned'(CVA6ConfigXlen)", "RVH: bit'(CVA6ConfigHExtEn)",
            "RVV: bit'(CVA6ConfigVExtEn)", "RVS: bit'(1)", "RVU: bit'(1)"],
        "hardware/deps/cva6/core/include/build_config_pkg.sv": [
            "cfg.FpgaEn = CVA6Cfg.FpgaEn;", "cfg.XLEN = CVA6Cfg.XLEN;",
            "cfg.IS_XLEN64 = IS_XLEN64;", "cfg.RVU = CVA6Cfg.RVU;", "cfg.RVH = CVA6Cfg.RVH;",
            "cfg.RVV = CVA6Cfg.RVV;", "cfg.RVS = CVA6Cfg.RVS;", "cfg.TvalEn = CVA6Cfg.TvalEn;",
            "bit FpPresent = CVA6Cfg.RVF | CVA6Cfg.RVD | CVA6Cfg.XF16 | CVA6Cfg.XF16ALT | CVA6Cfg.XF8 | CVA6Cfg.XF8ALT;",
            "cfg.FpPresent = bit'(FpPresent);"],
        "hardware/src/ara_soc.sv": [
            "DRAMBase = 64'h8000_0000", "cfg.NrPMPEntries = 0;", ".boot_addr_i (DRAMBase)",
            "CVA6AraConfig_user = gen_usr_cva6_config(cva6_config_pkg::cva6_cfg);",
            "CVA6AraConfig = build_config_pkg::build_config(CVA6AraConfig_user);",
            ".CVA6Cfg (CVA6AraConfig)", "cfg.RVF = FPUSupport[4];", "cfg.RVD = FPUSupport[5];"],
        "hardware/src/ara_system.sv": [".irq_i ('0)", ".ipi_i ('0)", ".time_irq_i ('0)", ".debug_req_i ('0)"]}
    source_text={}
    for relative,anchors in files.items():
        path=life.ROOT/relative
        require(str(path) in sources,"Missing frozen source: "+relative)
        pins=life.merge_pins(pins,{str(path):sources[str(path)]})
        require(life.digest(path)==sources[str(path)],"Frozen source drift")
        text=path.read_text();source_anchors(text,anchors);source_text[relative]=text
    soc=source_text["hardware/src/ara_soc.sv"]
    override=re.search(r"function automatic .*?gen_usr_cva6_config\(.*?endfunction",soc,re.S)
    require(override is not None and not set(re.findall(r"cfg\.(\w+)\s*=",override[0])) &
            {"XLEN","FpgaEn","RVU","RVS","RVH","RVV","TvalEn"},"Critical config overridden")
    selected=[p for p in sources if re.search(r"/cv(?:32|64).*_config_pkg\.sv$",p)]
    require(selected == [str(life.ROOT/"hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv")],
            "Ambiguous/different compiled config package")
    dispatcher=life.OUT/"old-image-source-evidence-20261006-01/ara_dispatcher.sv"
    require(pins.get(str(dispatcher)) == sources[str(life.ROOT/"hardware/src/ara_dispatcher.sv")],"Unbound frozen dispatcher")
    source_anchors(dispatcher.read_text(),[
        "`FF(csr_vstart_q, csr_vstart_d, '0)", "`FF(csr_vl_q, csr_vl_d, '0)",
        "`FF(csr_vtype_q, csr_vtype_d, '{vill: 1'b1, vsew: EW8, vlmul: LMUL_1, default: '0})",
        "`FF(csr_vxsat_q, csr_vxsat_d, '0)", "`FF(csr_vxrm_q, csr_vxrm_d, '0)"])
    design=Design(native.common.DESIGN)
    require(GPR_SCOPE in design.hierarchy and design.hierarchy[GPR_SCOPE].get("chksum") == "1875497202" and
            design.source(GPR_SCOPE)["resolved_path"] == str(life.ROOT/"hardware/deps/cva6/core/ariane_regfile_ff.sv") and
            not any(s.endswith(".i_ariane_regfile_fpga") for s in design.hierarchy),"Wrong elaborated FF GPR selection")
    return pins,dict(status="FROZEN_SOURCE_AND_ELABORATION_INITIAL_STATE_CONTRACT_VERIFIED",
        elaborated_GPR_scope=GPR_SCOPE,module_checksum="1875497202",reset_GPRs_all_zero=True,
        initial_privilege="M",XLEN=64,RVU=True,RVS=True,RVH=False,FpgaEn=False,PMPEntries=0,
        initial_mstatus="0xa00000000",initial_mtvec="0x80000040",initial_vtype="0x8000000000000000",
        initial_fflags=0,initial_vstart=0,initial_vl=0,initial_vxrm=0,initial_vxsat=0,
        no_external_interrupts=True,ELF_no_compressed_instructions=True,
        dirty_and_MRET_source_anchors_verified=True,scope="This sealed M-mode ELF only; not general CPU/MMU equivalence")


def signed(value, bits):
    value &= (1 << bits)-1
    return value-(1 << bits) if value >> (bits-1) else value


class Model:
    """No DUT values enter this state; step() accepts no observed retirement."""
    def __init__(self, blob, symbols):
        require(blob[:6] == b"\x7fELF\x02\x01", "Expected ELF64 little endian")
        header = struct.unpack_from("<HHIQQQIHHHHHH", blob,16)
        require(header[0] == 2 and header[1] == 243 and header[8] == 56, "Wrong ELF ABI")
        require(not header[6]&1,"ELF compressed ISA flag outside sealed scope")
        self.pc = header[3]
        require(self.pc == 0x80000000, "Wrong sealed entry")
        self.memory, self.executable = {}, set()
        for i in range(header[9]):
            kind, flags, off, address, _, size, total, _ = struct.unpack_from("<IIQQQQQQ",blob,header[4]+56*i)
            if kind != 1: continue
            require(size <= total and off+size <= len(blob) and
                    0x80000000 <= address <= address+total <= 0x80200000, "Bad ELF segment")
            for index in range(total):
                require(address+index not in self.memory,"Overlapping ELF segments")
                self.memory[address+index] = blob[off+index] if index < size else 0
            if flags & 1:
                require(address%4 == size%4 == 0,"Compressed/truncated executable")
                self.executable.update(range(address,address+size,4))
        self.symbols = dict(symbols)
        # The elaborated ASIC FF GPR file resets all words to zero; CSR reset
        # plus fixed UXL/SXL and boot-vector updates are independently source-pinned.
        self.gpr = [0]*32
        self.csr = {a:0 for a in (1,8,9,10,0xc20,0xc21,0x300,0x302,0x304,0x305,0x341,0x342,0x343)}
        self.csr.update({0x300:0xa00000000,0x305:0x80000040,0xc21:1<<63})
        self.vrf = [None]*32
        self.context = None
        self.commands, self.vector_effects, self.traps = [], [], []
        self.counts = Counter()
        self.steps = 0
        self.terminal = False

    def read(self,address,size):
        require(0x80000000 <= address and address+size <= 0x80200000 and
                all(address+i in self.memory for i in range(size)), "Unknown/outside memory read")
        return bytes(self.memory[address+i] for i in range(size))

    def write(self,address,data):
        require(0x80000000 <= address and address+len(data) <= 0x80200000 and
                not any((address+i)&~3 in self.executable for i in range(len(data))),
                "Outside/self-modifying memory write")
        self.memory.update({address+i:v for i,v in enumerate(data)})

    def dirty(self,vector=False):
        shift = 9 if vector else 13
        self.csr[0x300] |= (3 << shift) | (1 << 63)

    def csr_write(self,address,value):
        require(address in self.csr and address not in (0xc20,0xc21), "Unknown/read-only CSR write")
        if address == 1:
            value &= 31; self.dirty()
        elif address in (9,10):
            value &= 1 if address == 9 else 3; self.dirty(True)
        elif address == 8:
            require(value == 0,"Only scoped vstart0 writes supported"); self.dirty(True)
        elif address == 0x300:
            require(value == (0xa00000000 | 0x6600), "Unsupported mstatus mutation")
        elif address in (0x302,0x304):
            require(value == 0,"Delegation/interrupt enabling outside contract")
        elif address == 0x305:
            require(value%4 == 0 and value in self.executable,"Invalid trap vector")
        elif address == 0x341:
            require(value%4 == 0 and value in self.executable,"Invalid exception return PC")
        elif address in (0x342,0x343):
            raise ValueError("Direct cause/tval writes outside scoped ELF")
        self.csr[address] = value & MASK

    def vector(self,word):
        opcode, reg, rs1 = word&127,(word>>7)&31,(word>>15)&31
        if opcode == 0x57:
            require(word == 0x0082f057 and self.gpr[rs1] == 64,"Unsupported vector configuration")
            self.csr.update({0xc20:min(self.gpr[rs1],128//2),0xc21:8,8:0})
            self.dirty(True); self.counts["vset"] += 1
            return
        require(word & ~(31<<15 | 31<<7) == (0x02005007 if opcode == 7 else 0x02005027) and
                self.csr[0xc20] == 64 and self.csr[0xc21] == 8 and self.csr[8] == 0,
                "Unsupported vector memory instruction/state")
        address = self.gpr[rs1]
        require(address%2 == 0,"Misaligned vector memory")
        if opcode == 7:
            require(reg == self.counts["vload"] < 32,"Reordered/extra seed load")
            data = self.read(address,128)
            self.vrf[reg] = bytearray(data)
            self.vector_effects.append(dict(word=word,vd=reg,data=data.hex(),kind="seed"))
            self.counts["vload"] += 1
        else:
            require(reg == self.counts["vstore"]%32 and self.counts["vstore"] < 128 and
                    self.vrf[reg] is not None,"Unknown/reordered snapshot source")
            data = bytes(self.vrf[reg]); self.write(address,data)
            self.counts["vstore"] += 1
        self.dirty(True)

    def custom(self,word):
        phase = len(self.commands)
        require(phase < 8 and word == native.WORDS[phase],"Unknown/reordered custom")
        require(self.csr[8] == 0 and self.csr[0xc20] == 64 and self.csr[0xc21] == 8,
                "Custom vector state outside contract")
        fault, data, vd = False, b"", None
        if phase == 0:
            address = self.gpr[10]
            require(address%64 == 0 and self.gpr[11] == 0,"Invalid FULL operand")
            descriptor = struct.unpack("<4B2H4I5Q",self.read(address,64))
            require(descriptor[:10] == (1,1,1,0,64,1,128,128,128,0) and
                    descriptor[13:] == (0,0) and all(a%64 == 0 for a in descriptor[10:13]),
                    "FULL descriptor outside independent D64/tile1 model")
            self.context = dict(ready=True,head=descriptor[4],tokens=descriptor[5],
                rows=[self.read(a,128) for a in descriptor[10:13]])
        elif phase in (1,2,3):
            require(self.context and self.context["ready"],"COLUMN without context")
            selector = self.gpr[10]
            dimension = selector & 127
            fault = selector >> 8 != 0 or dimension >= self.context["head"]
            require(selector == (63,64,63)[phase-1],"Wrong scoped column selector")
            if not fault:
                vd = (word>>7)&31
                data = self.context["rows"][1+(selector>>7 & 1)][2*dimension:2*dimension+2]
                require(self.vrf[vd] is not None,"Unseeded COLUMN destination")
                self.vrf[vd][:len(data)] = data
        elif phase in (4,5,6):
            selector = self.gpr[10]
            require(self.context and self.context["ready"] and selector == phase-4,"Invalid scoped row")
            vd = (word>>7)&31
            data = self.context["rows"][selector]
            self.vrf[vd] = bytearray(data)
        else:
            require(self.context and self.context["ready"],"RELEASE without context")
            self.context["ready"] = False
        self.commands.append(dict(phase=phase,word=word,pc=self.pc,selector=self.gpr[10],
                                  fault=fault,vd=vd,write_bytes=len(data)))
        if data:
            self.vector_effects.append(dict(word=word,vd=vd,data=data.hex(),kind="custom",phase=phase))
        if fault:
            require(self.pc == self.symbols["boundary_bad"] and self.csr[0x302] == 0 and
                    self.csr[0x304] == 0 and not self.traps,"Unexpected independent custom fault")
            self.csr.update({0x341:self.pc,0x342:2,0x343:0})
            status = self.csr[0x300]
            self.csr[0x300] = (status & ~((1<<3)|(1<<7)|(3<<11))) | ((status>>3 & 1)<<7) | (3<<11)
            self.traps.append(dict(pc=self.pc,cause=2,tval=0,handler=self.csr[0x305]))
            return self.csr[0x305]
        self.dirty(True)
        return self.pc+4

    def step(self):
        require(not self.terminal and self.pc in self.executable,"Unknown/terminal executable PC")
        pc = self.pc
        word = int.from_bytes(self.read(pc,4),"little")
        op,rd,f3,rs1,rs2,f7 = word&127,(word>>7)&31,(word>>12)&7,(word>>15)&31,(word>>20)&31,word>>25
        a,b = self.gpr[rs1],self.gpr[rs2]
        immediate = signed(word>>20,12)
        nxt,value,dest = pc+4,None,0
        effect = dict(pc=pc,insn=word,rd=0,mem_addr=0,mem_rmask=0,mem_wmask=0,trap=0)
        if op == 0x13:
            dest = rd
            if f3 == 0: value = a+immediate
            elif f3 == 1 and word>>26 == 0: value = a << ((word>>20)&63)
            elif f3 == 6: value = a | (immediate&MASK)
            else: raise ValueError("Unsupported OP-IMM")
            self.counts["integer"] += 1
        elif op == 0x33:
            require(f7 == 0 and f3 in (0,3,4,6),"Unsupported OP/M/W")
            value = {0:lambda:a+b,3:lambda:int(a<b),4:lambda:a^b,6:lambda:a|b}[f3]()
            dest=rd; self.counts["integer"] += 1
        elif op in (0x17,0x37):
            value = signed(word & 0xfffff000,32)+(pc if op == 0x17 else 0)
            dest=rd; self.counts["integer"] += 1
        elif op in (3,0x23):
            require(f3 in ((1,2,3,5) if op == 3 else (1,2,3)),"Unsupported scalar memory width")
            size = 1 << (f3&3)
            offset = immediate if op == 3 else signed((word>>25)<<5 | ((word>>7)&31),12)
            address = (a+offset)&MASK
            require(address%size == 0 and (address&7)+size <= 8,"Misaligned/cross-word scalar memory")
            mask = ((1<<size)-1) << (address&7)
            effect["mem_addr"] = address
            if op == 3:
                raw = int.from_bytes(self.read(address,size),"little")
                value = signed(raw,size*8) if f3 in (1,2) else raw
                dest=rd; effect["mem_rmask"] = mask; self.counts["scalar_loads"] += 1
            else:
                data = (b & ((1<<(8*size))-1)).to_bytes(size,"little")
                self.write(address,data)
                effect.update(mem_wmask=mask,store_value=int.from_bytes(data,"little"),store_size=size)
                self.counts["scalar_stores"] += 1
                if address == self.symbols["tohost"]:
                    require(size == 8 and b == 1,"Independent terminal oracle failure")
                    self.terminal=True
        elif op == 0x63:
            require(f3 in (0,1,7),"Unsupported conditional branch")
            offset = signed(((word>>31)<<12)|((word>>7&1)<<11)|((word>>25&63)<<5)|((word>>8&15)<<1),13)
            taken = {0:a==b,1:a!=b,7:a>=b}[f3]
            nxt = pc+offset if taken else pc+4
            self.counts["branches"] += 1
        elif op in (0x6f,0x67):
            if op == 0x6f:
                offset = signed(((word>>31)<<20)|((word>>12&255)<<12)|((word>>20&1)<<11)|((word>>21&1023)<<1),21)
                nxt = pc+offset
            else:
                require(f3 == 0,"Unsupported JALR")
                nxt = (a+immediate)&~1
            value=pc+4;dest=rd; self.counts["jumps"] += 1
        elif op == 0x73:
            if word == 0x30200073:
                require(len(self.traps) == 1 and not self.counts["mret"] and
                        self.csr[0x341] == self.traps[0]["pc"]+4 and
                        (self.csr[0x300]>>11)&3 == 3,"Unsupported MRET state")
                nxt=self.csr[0x341]
                status=self.csr[0x300]
                self.csr[0x300]=(status&~((1<<3)|(1<<7)|(3<<11)))|((status>>7 & 1)<<3)|(1<<7)
                self.counts["mret"] += 1
            else:
                address=word>>20
                require(address in self.csr and f3 in (1,2,5),"Unsupported CSR/system instruction")
                value=self.csr[address];dest=rd
                operand=rs1 if f3 == 5 else a
                if f3 in (1,5) or rs1:
                    self.csr_write(address,operand if f3 in (1,5) else value|operand)
                self.counts["csr"] += 1
        elif op in (7,0x27,0x57):
            self.vector(word)
        elif op == 0x5b:
            before=len(self.traps);nxt=self.custom(word)
            effect["trap"]=int(len(self.traps)>before)
        else:
            raise ValueError("Unknown opcode 0x%x at 0x%x" % (op,pc))
        require(nxt%4 == 0,"Unsupported compressed/control-flow target")
        if dest:
            require(value is not None,"Missing GPR result")
            self.gpr[dest]=value&MASK
            effect.update(rd=dest,rd_wdata=value&MASK)
        self.gpr[0]=0
        self.pc=nxt&MASK;self.steps+=1
        return effect


def compare_retirement(expected,actual,order):
    for key in ("pc","insn","rd","mem_addr","mem_rmask","mem_wmask","trap"):
        require(actual[key] == expected[key],"Retirement %d %s mismatch: expected=%s actual=%s" %
                (order,key,hex(expected[key]),hex(actual[key])))
    if expected["rd"]:
        require(actual["rd_wdata"] == expected["rd_wdata"],"Retirement %d GPR result mismatch" % order)
    if expected["mem_wmask"]:
        mask=(1 << (8*expected["store_size"]))-1
        require(actual["mem_wdata"]&mask == expected["store_value"],"Retirement %d scalar store data mismatch" % order)


def replay(blob,symbols,rows,timeout=60,max_steps=300000):
    model=Model(blob,symbols)
    retires=[r for r in rows if r["event"] == "retire"]
    require(retires and [r["order"] for r in retires] == list(range(len(retires))),"Incomplete retirement sequence")
    deadline=time.monotonic()+timeout
    index=0;gpr_writes=0
    while not model.terminal:
        require(model.steps<max_steps and time.monotonic()<deadline,"Independent replay bound exceeded")
        expected=model.step()
        if expected["trap"]:
            # Model-derived precise exception is absent from this sealed RVFI
            # retirement stream, but must have exactly matching CVX/handler evidence.
            require(index < len(retires) and retires[index]["pc"] == model.pc,
                    "Precise model trap does not enter independently derived mtvec")
            continue
        require(index<len(retires),"Partial scalar trace")
        compare_retirement(expected,retires[index],index)
        gpr_writes+=bool(expected["rd"]);index+=1
    require(index==len(retires),"Extra post-terminal retirement")
    require(model.counts["vload"] == 32 and model.counts["vstore"] == 128 and model.counts["vset"] == 5 and
            model.counts["csr"] == 37 and model.counts["mret"] == 1 and len(model.commands) == 8 and
            [c["fault"] for c in model.commands] == [False,False,True,False,False,False,False,False] and
            sum(c["write_bytes"] for c in model.commands) == 388,"Independent model workload differs")
    for address,value in native.expected_memory(symbols).items():
        require(model.memory.get(address)==value,"Independent final signature/VRF/CSR memory differs")
    return model,dict(status="COMPLETE_BOUNDED_INDEPENDENT_SCALAR_ISA_AND_AKV_MODEL_MATCH_NOT_ADMISSION",
        matched_retirements=index,independently_executed_steps=model.steps,matched_GPR_writes=gpr_writes,
        matched_scalar_loads=model.counts["scalar_loads"],matched_scalar_stores=model.counts["scalar_stores"],
        instruction_counts=dict(model.counts),independently_derived_traps=model.traps,
        skipped_retirements=0,unknown_state_reads=0,mismatches=0,
        full_scalar_independent_qualified=True,full_scalar_differential_qualified=False,
        native_Spike_comparison=False,coverage_admitted=False)


def bind_native_effects(model,arch,rows):
    require(len(model.commands) == len(arch["commands"]) == 8,"Custom ledger lengths differ")
    for expected,actual in zip(model.commands,arch["commands"]):
        require(expected["word"] == actual["word"] and int(expected["fault"]) == actual["fault"],
                "Independent command/native outcome mismatch")
    allocations=[r for r in arch["uops"] if r["insn"]&127 == 7]
    require(len(allocations) == 32,"Missing seed allocations")
    command_seq={r["phase"]:r["seq"] for r in arch["commands"]}
    expected={}
    seed_index=0
    for effect in model.vector_effects:
        seq=allocations[seed_index]["order"] if effect["kind"] == "seed" else command_seq[effect["phase"]]
        if effect["kind"] == "seed":seed_index+=1
        require(seq not in expected,"Duplicate independent vector effect")
        data=bytes.fromhex(effect["data"])
        expected[seq]={(effect["vd"],i):v for i,v in enumerate(data)}
    accepted={seq:{} for seq in expected}
    for r in rows:
        if r["event"] != "write":continue
        seq=int(r["arch_seq"]);be=int(r["be"],16)
        if not be:continue  # Frozen native validator separately binds all six BE0 events.
        require(seq in expected,"Unexpected granted vector writer")
        reg,chunk=divmod(int(r["addr"]),4);lane=int(r["lane"])
        require(0 <= lane < 4 and 0 < be < 256,"Malformed physical vector write")
        word=int(r["wdata"],16)
        for physical in range(8):
            if be>>physical&1:
                slot,within=divmod(physical,2)
                natural=((slot&1)<<1)|(slot>>1)
                key=(reg,chunk*32+(natural*4+lane)*2+within)
                require(key in expected[seq] and key not in accepted[seq],"Unexpected/duplicate vector byte")
                value=word>>(8*physical)&255
                require(value == expected[seq][key],"Independent model/native vector byte mismatch")
                accepted[seq][key]=value
    require(accepted == expected,"Incomplete independent/native vector effects")
    return dict(status="INDEPENDENT_MODEL_BYTES_EXACTLY_BOUND_TO_NATIVE_WRITES",
                matched_seed_bytes=4096,matched_custom_bytes=388,
                expected_values_not_derived_from_DUT=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(),"Fresh direct output required")
    path=CANDIDATE/"candidate-seal.json"
    seal=life.read_bound(path,CANDIDATE_SHA)
    require(not (CANDIDATE/"failure.json").exists(),"Rejected candidate")
    pins=life.merge_pins(seal["input_pins"],seal["output_pins"])
    pins=life.merge_pins(pins,{str(path):CANDIDATE_SHA})
    manifest=life.read_bound(native.RUN/"manifest.json",native.RUN_SEAL)
    pre=manifest["preflight"];elf=Path(pre["input_elf"])
    require(pins.get(str(elf)) == ELF_SHA,"Wrong sealed ELF")
    source_manifest=native.software.BUILD/"build-source-pins.json"
    sources=life.read_bound(source_manifest,pins[str(source_manifest)])
    for rel in ("hardware/deps/cva6/core/ariane_regfile_ff.sv","hardware/deps/cva6/core/issue_read_operands.sv",
                "hardware/deps/cva6/core/csr_regfile.sv","hardware/deps/cva6/core/decoder.sv"):
        p=life.ROOT/rel;pins=life.merge_pins(pins,{str(p):sources[str(p)]})
    for p in (Path(__file__).resolve(),Path(__file__).with_name("test_akv_column_scalar_oracle.py")):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    pins,contract=source_contract(sources,pins)
    life.check(pins)
    symbols=dict(pre["symbols"])
    for name in ("query","key","value","descriptor","seed"):
        symbols[name]=native.software.shared._elf_symbol(elf,native.software.shared.LLVM/"llvm-readelf",name)
    out.mkdir()
    try:
        rows=native.commit_rows(native.RUN/"commit_trace.csv")
        model,result=replay(elf.read_bytes(),symbols,rows)
        arch=native.commit_audit(rows,symbols,elf.read_bytes())
        require(model.traps == [dict(pc=symbols["boundary_bad"],cause=2,tval=0,handler=symbols["boundary_handler"])] and
                [int(c["fault"]) for c in model.commands] == [c["fault"] for c in arch["commands"]],
                "Independent trap model/native lifecycle disagreement")
        native.vector_audit(native.RUN/"vector_trace.csv",arch)
        effects=bind_native_effects(model,arch,native.common.read_csv(native.RUN/"vector_trace.csv",native.common.VECTOR_FIELDS))
        native.stdout_audit((native.RUN/"run.vcs.log").read_text())
        life.check(pins)
        for name,value in (("scalar-qualification.json",result),("source-contract.json",contract),
                           ("independent-custom-ledger.json",model.commands),
                           ("independent-native-byte-binding.json",effects)):
            life.save(out/name,value)
        life.save(out/"qualification-seal.json",dict(input_pins=pins,
            output_pins={str(p):life.digest(p) for p in out.iterdir()},coverage_admitted=False))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/"qualification-seal.json"),result=result)))
    except Exception as error:
        life.save(out/"failure.json",dict(status="INDEPENDENT_SCALAR_ORACLE_REJECTED_NOT_ADMITTED",reason=str(error)))
        raise


if __name__ == "__main__":
    main()
