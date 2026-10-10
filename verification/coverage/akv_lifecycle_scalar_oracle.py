"""Independent bounded ISA/lifecycle model for the sealed lifecycle v2 ELF.

No retirement or accelerator observation is an input to Model.step().
This module does not run a simulator or approve a coverage population.
"""
import hashlib
import struct
import time

import akv_column_scalar_oracle as base
import build_akv_lifecycle_preflight as fixture
import run_akv_lifecycle_simulation as runner

require, MASK, signed = base.require, base.MASK, base.signed


class Model(base.Model):
    def __init__(self, blob, symbols):
        require(hashlib.sha256(blob).hexdigest() == runner.ELF_SHA,
                "Wrong lifecycle ELF")
        fixture.native_elf_audit(blob, symbols)
        super().__init__(blob, symbols)
        self.requests = []

    def vector(self, word):
        op, reg, rs1 = word & 127, word >> 7 & 31, word >> 15 & 31
        if op == 0x57:
            require(self.counts["vset"] < 11, "Extra VSET")
            return super().vector(word)
        require(op in (7, 0x27) and word & ~(31 << 15 | 31 << 7) ==
                (0x02005007 if op == 7 else 0x02005027) and
                (self.csr[0xc20], self.csr[0xc21], self.csr[8]) == (64, 8, 0),
                "Unsupported vector memory/state")
        address = self.gpr[rs1]
        if op == 7:
            require(reg == self.counts["vload"] < 32 and
                    address == self.symbols["lifecycle_seed"] + 64 + reg * 128,
                    "Wrong seed register/address")
            data = self.read(address, 128)
            require(data == fixture.expected_seed()[64+reg*128:64+(reg+1)*128], "Wrong seed bytes")
            self.vrf[reg] = bytearray(data)
            self.vector_effects.append(dict(word=word, vd=reg, data=data.hex(), kind="seed", pc=self.pc))
            self.counts["vload"] += 1
        else:
            phase, expected_reg = divmod(self.counts["vstore"], 32)
            require(phase < 10 and reg == expected_reg and len(self.commands) == phase+1 and
                    address == self.symbols["lifecycle_snapshots"] + phase*4224 + 64 + reg*128 and
                    self.vrf[reg] is not None, "Wrong snapshot register/address/order")
            data = bytes(self.vrf[reg])
            require(data == fixture.expected_frame(phase)[64+reg*128:64+(reg+1)*128],
                    "Independent VRF frame differs")
            self.write(address, data)
            self.counts["vstore"] += 1
        self.dirty(True)

    def custom(self, word):
        phase = len(self.commands)
        require(phase < 10 and word == fixture.WORDS[phase] and
                self.pc == self.symbols["lifecycle_site_"+str(phase)] and
                self.counts["vload"] == 32 and self.counts["vstore"] == phase*32 and
                (self.csr[8], self.csr[0xc20], self.csr[0xc21]) == (0, 64, 8),
                "Custom instruction/site/vector state outside contract")
        a, b = self.gpr[10], self.gpr[11]
        error, data, vd = 0, b"", None
        if word == 0x0000505b:
            require(a == b == 0, "Release operands")
            self.context = None
        elif word in (0x00b5605b, 0x00b5205b):
            require(a == self.symbols["lifecycle_descriptor"] and b == 0 and a % 64 == 0,
                    "FULL operands")
            descriptor = struct.unpack("<4B2H4I5Q", self.read(a, 64))
            source = self.symbols["lifecycle_sources"]
            require(descriptor == (1,1,1,0,64,1,128,128,128,0,source+64,source+320,source+576,0,0),
                    "FULL descriptor differs")
            self.context = dict(v2=word == 0x00b5605b, head=64, tokens=1,
                                rows=[self.read(p, 128) for p in descriptor[10:13]])
        elif word in (0x02a0605b, 0x02a0205b):
            require(b == 0 and a == (1 if phase == 6 else 0), "REFILL operands")
            if self.context is None or self.context["v2"] != (word == 0x02a0605b):
                error = 12
            elif a >= self.context["tokens"]:
                error = 11
            else:
                raise ValueError("Successful refill outside bounded lifecycle")
            self.context = None
        else:
            require(word in (0x0405345b, 0x0005345b) and a == b == 0, "ROW operands")
            dimension = 96 if word == 0x0405345b else 64
            if self.context is None:
                error = 12
            elif dimension != self.context["head"] or (dimension == 96 and not self.context["v2"]):
                error = 6
            else:
                vd, data = 8, self.context["rows"][0]
                self.vrf[vd] = bytearray(data)
        self.commands.append(dict(phase=phase, word=word, pc=self.pc, selector=a, rs2=b,
                                  fault=bool(error), validation_error=error, vd=vd,
                                  write_bytes=len(data), context_ready_after=self.context is not None))
        if data:
            self.vector_effects.append(dict(word=word, vd=vd, data=data.hex(), kind="custom", phase=phase, pc=self.pc))
        if error:
            require(self.csr[0x302] == self.csr[0x304] == 0 and
                    self.csr[0x305] == self.symbols["lifecycle_handler"], "Trap environment differs")
            self.csr.update({0x341:self.pc, 0x342:2, 0x343:0})
            status = self.csr[0x300]
            self.csr[0x300] = (status & ~((1<<3)|(1<<7)|(3<<11))) | ((status>>3 & 1)<<7) | (3<<11)
            self.traps.append(dict(pc=self.pc, cause=2, tval=0, handler=self.csr[0x305]))
            return self.csr[0x305]
        self.dirty(True)
        return self.pc+4

    def step(self):
        require(not self.terminal and self.pc in self.executable, "Unknown/terminal PC")
        pc = self.pc
        w = int.from_bytes(self.read(pc, 4), "little")
        op, rd, f3, rs1, rs2, f7 = w&127, w>>7&31, w>>12&7, w>>15&31, w>>20&31, w>>25
        a, b = self.gpr[rs1], self.gpr[rs2]
        nxt, value = pc+4, None
        effect = dict(pc=pc, insn=w, rd=0, mem_addr=0, mem_rmask=0, mem_wmask=0, trap=0)
        if w == 0x30200073:
            index = self.counts["mret"]
            require(index < len(self.traps) and self.csr[0x341] == self.traps[index]["pc"]+4 and
                    self.csr[0x300]>>11&3 == 3, "MRET mismatch")
            nxt = self.csr[0x341]
            s = self.csr[0x300]
            self.csr[0x300] = (s & ~((1<<3)|(1<<7)|(3<<11))) | ((s>>7&1)<<3) | (1<<7)
            self.counts["mret"] += 1
        elif op in (0x13, 0x1b, 0x33, 0x3b):
            bits = 32 if op in (0x1b, 0x3b) else 64
            immediate = op in (0x13, 0x1b)
            rhs = signed(w>>20, 12) & MASK if immediate else b
            sh = (w>>20 if immediate else b) & (bits-1)
            if immediate:
                require((op == 0x13 or f3 in (0,1,5)) and
                        (f3 not in (1,5) or (w>>(25 if bits == 32 else 26)) in
                         ((0,) if f3 == 1 else (0, 0x20 if bits == 32 else 0x10))), "Invalid immediate encoding")
            else:
                require(f7 in (0,0x20,1) and (f7 != 0x20 or f3 in (0,5)) and
                        (op != 0x3b or f3 in (0,1,5)) and (f7 != 1 or (op == 0x33 and f3 == 3)),
                        "Unsupported register/M encoding")
            if not immediate and f7 == 1:
                value = a*b >> 64
            elif f3 == 0:
                value = a-rhs if not immediate and f7 == 0x20 else a+rhs
            elif f3 == 1: value = a << sh
            elif f3 == 2: value = int(signed(a,64) < signed(rhs,64))
            elif f3 == 3: value = int(a < rhs)
            elif f3 == 4: value = a ^ rhs
            elif f3 == 5:
                arithmetic = (w>>30)&1
                value = signed(a,bits) >> sh if arithmetic else (a & ((1<<bits)-1)) >> sh
            elif f3 == 6: value = a | rhs
            elif f3 == 7: value = a & rhs
            else: raise ValueError("Unknown integer encoding")
            if bits == 32: value = signed(value, 32)
            self.counts["integer"] += 1
        elif op == 0x63:
            require(f3 in (0,1,4,5,6,7), "Invalid branch encoding")
            offset = signed((w>>31<<12)|(w>>7&1)<<11|(w>>25&63)<<5|(w>>8&15)<<1,13)
            taken = {0:a==b,1:a!=b,4:signed(a,64)<signed(b,64),5:signed(a,64)>=signed(b,64),
                     6:a<b,7:a>=b}[f3]
            nxt = pc+offset if taken else pc+4
            self.counts["branches"] += 1
        elif op in (3,0x23) and f3 in (0,4,6):
            require(op == 3 or f3 == 0, "Invalid store width")
            size = 1 << (f3&3)
            imm = signed(w>>20,12) if op == 3 else signed((w>>25<<5)|(w>>7&31),12)
            address = (a+imm)&MASK
            require(address%size == 0 and (address&7)+size <= 8, "Misaligned scalar memory")
            effect["mem_addr"] = address
            mask = ((1<<size)-1) << (address&7)
            if op == 3:
                value = int.from_bytes(self.read(address,size),"little")
                if f3 == 0: value = signed(value,8)
                effect["mem_rmask"] = mask
                self.counts["scalar_loads"] += 1
            else:
                self.write(address,bytes([b&255]))
                effect.update(mem_wmask=mask,store_value=b&255,store_size=1)
                self.counts["scalar_stores"] += 1
        elif op == 0x0f:
            require(w == 0x0330000f, "Unsupported fence/system effect")
            self.counts["fence"] += 1
        else:
            return super().step()
        require(nxt%4 == 0, "Unaligned control target")
        if value is not None and rd:
            self.gpr[rd] = value & MASK
            effect.update(rd=rd, rd_wdata=value&MASK)
        self.gpr[0] = 0
        self.pc, self.steps = nxt&MASK, self.steps+1
        return effect


def expected_memory(symbols):
    regions = {
        "lifecycle_seed":fixture.expected_seed(), "lifecycle_sources":fixture.expected_sources(),
        "lifecycle_snapshots":b"".join(fixture.expected_frame(p) for p in range(10)),
        "lifecycle_csrs":struct.pack("<60Q",*([21,0,64,8,2,1]*10)),
        "lifecycle_status":struct.pack("<10I",*fixture.FAULTS),
        "lifecycle_scan":struct.pack("<20I",*([512,0]*10)),
        "lifecycle_trap_count":struct.pack("<Q",4), "lifecycle_expected_pc":bytes(8),
        "lifecycle_semantic_errors":bytes(16), "g75_trap":bytes(24),
        "g75_result":struct.pack("<2I",7740,0), "num_failed":bytes(4), "tohost":struct.pack("<Q",1),
        "lifecycle_traps":struct.pack("<12Q",*[v for p in fixture.BAD_PHASES
                            for v in (2,symbols["lifecycle_site_"+str(p)],0)])}
    s = symbols["lifecycle_sources"]
    regions["lifecycle_descriptor"] = struct.pack("<4B2H4I5Q",1,1,1,0,64,1,128,128,128,0,s+64,s+320,s+576,0,0)
    memory = {}
    for name, data in regions.items():
        for offset, value in enumerate(data):
            address = symbols[name]+offset
            require(address not in memory, "Overlapping architectural regions")
            memory[address] = value
    return memory


def finish(model):
    require(model.terminal and model.counts["vload"] == 32 and model.counts["vstore"] == 320 and
            model.counts["vset"] == 11 and model.counts["mret"] == 4 and model.counts["csr"] == 85 and
            len(model.commands) == 10,
            "Incomplete lifecycle workload")
    reference = fixture.reference_lifecycle()
    require([c["validation_error"] for c in model.commands] == reference["validation_errors"] and
            [c["context_ready_after"] for c in model.commands] == reference["context_ready_after"] and
            [c["write_bytes"] for c in model.commands] == reference["custom_write_bytes"],
            "Independent lifecycle differs")
    require(model.traps == [dict(pc=model.symbols["lifecycle_site_"+str(p)],cause=2,tval=0,
                                handler=model.symbols["lifecycle_handler"]) for p in fixture.BAD_PHASES],
            "Trap ledger differs")
    for address, value in expected_memory(model.symbols).items():
        require(model.memory.get(address) == value, "Independent final memory differs at %x" % address)


def replay(blob, symbols, rows=None, timeout=120, max_steps=1000000):
    model = Model(blob, symbols)
    retires = None if rows is None else [r for r in rows if r["event"] == "retire"]
    if retires is not None:
        require(retires and [r["order"] for r in retires] == list(range(len(retires))), "Partial retirement sequence")
    deadline, index, writes = time.monotonic()+timeout, 0, 0
    while not model.terminal:
        require(model.steps < max_steps and time.monotonic() < deadline, "Replay bound exceeded")
        word = int.from_bytes(model.read(model.pc,4),"little")
        if base.native.request_instruction(word):
            model.requests.append(dict(pc=model.pc,word=word,rd=word>>7&31,
                response_value=model.csr[word>>20] if word&127 == 0x73 else 64 if word&127 == 0x57 else 0,
                step=model.steps))
        effect = model.step()
        if retires is None: continue
        if effect["trap"]:
            require(index < len(retires) and retires[index]["pc"] == model.pc,
                    "Precise trap missing handler entry")
            continue
        require(index < len(retires), "Incomplete scalar trace")
        base.compare_retirement(effect, retires[index], index)
        writes += bool(effect["rd"])
        index += 1
    if retires is not None: require(index == len(retires), "Extra post-terminal retirement")
    finish(model)
    return model, dict(status="LIFECYCLE_INDEPENDENT_MODEL_COMPLETE" if retires is None else
                      "LIFECYCLE_COMPLETE_INDEPENDENT_SCALAR_MATCH_NOT_ADMISSION",
        independently_executed_steps=model.steps, matched_retirements=index, matched_GPR_writes=writes,
        instruction_counts=dict(model.counts), independently_derived_traps=model.traps,
        full_scalar_independent_qualified=retires is not None, full_scalar_differential_qualified=False,
        skipped_retirements=0, unknown_state_reads=0, mismatches=0, coverage_admitted=False)
