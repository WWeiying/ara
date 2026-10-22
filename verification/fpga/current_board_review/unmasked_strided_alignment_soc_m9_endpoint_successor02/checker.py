#!/usr/bin/env python3
"""Strict real-ELF endpoint contracts; retain sealed memory-owner/data checks."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent/'unmasked_strided_alignment_soc_m9_checker_successor01'
spec = importlib.util.spec_from_file_location('owner_successor', PREVIOUS/'checker.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
c = previous.old.c
BASE = previous.BASE
need = c.need
PLAN_SHA = '0e73362c293a7b4937f8a03a580371e0b92c1b3ae21303f50d800af5c19eafdf'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


class Elf:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        need(self.data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', self.data, 18)[0] == 243,
             'Actual RV64 little-endian ELF')

    def tables(self, offset_at, size_at, count_at, fmt):
        off = struct.unpack_from('<Q', self.data, offset_at)[0]
        size = struct.unpack_from('<H', self.data, size_at)[0]
        count = struct.unpack_from('<H', self.data, count_at)[0]
        need(size == struct.calcsize(fmt), 'ELF entry size')
        return [struct.unpack_from(fmt, self.data, off+i*size) for i in range(count)]

    def insn(self, pc):
        for p in self.tables(32, 54, 56, '<IIQQQQQQ'):
            if p[0] == 1 and p[3] <= pc < p[3]+p[5]:
                off = p[2]+pc-p[3]
                half = int.from_bytes(self.data[off:off+2], 'little')
                return int.from_bytes(self.data[off:off+(4 if half & 3 == 3 else 2)], 'little')
        raise ValueError('Instruction absent from actual ELF')

    def symbol(self, name):
        sections = self.tables(40, 58, 60, '<IIQQQQIIQQ')
        found = []
        for s in sections:
            if s[1] != 2:
                continue
            strings = sections[s[6]]
            table = self.data[strings[4]:strings[4]+strings[5]]
            need(s[9] == 24, 'ELF symbol entry size')
            for off in range(s[4], s[4]+s[5], s[9]):
                n, _, _, defined, value, _ = struct.unpack_from('<IBBHQQ', self.data, off)
                if defined and table[n:table.index(b'\0', n)].decode() == name:
                    found.append(value)
        need(len(found) == 1, 'Unique defined actual ELF symbol '+name)
        return found[0]


def bind(member, backend):
    need(member in ('load_m', 'store_m', 'load_sv39', 'store_sv39') and backend in ('dut', 'spike'),
         'Explicit supported member/backend')
    plan_path = BASE/'vcs_m9_prepared01/plan.json'
    need(sha(plan_path) == PLAN_SHA, 'Original immutable plan')
    pins = json.loads(plan_path.read_text())['pins']
    ref = BASE/('reference_'+member+'01')
    flavor = 'soc' if backend == 'dut' else 'spike'
    path = ref/(flavor+'.spec.json')
    need(sha(path) == pins[str(path)], 'Original spec pin')
    spec = json.loads(path.read_text())
    elf_path = ref/(flavor+'.elf')
    need(spec['elf'] == str(elf_path) and sha(elf_path) == spec['elf_sha256'] == pins[str(elf_path)],
         'Original actual ELF pin')
    elf = Elf(elf_path)
    s = spec['symbols']
    entry = elf.symbol('replay_exit')
    need(s['replay_exit'] == entry, 'ELF exit symbol')
    if backend == 'dut':
        address, value, store_pc = 0xd0000000, 0, entry+10
        expected = {entry: 0x00d0029b, entry+4: 0x02f2,
                    entry+6: 0x0330000f, store_pc: 0x00a2b023}
    else:
        # No optional/fabricated symbol: require the pinned ELF's actual HTIF symbol.
        address, value, store_pc = elf.symbol('tohost'), 1, entry+18
        need(s['tohost'] == address, 'Spec versus actual ELF tohost')
        upper, lower = elf.insn(entry+6), elf.insn(entry+10)
        need(upper & 0xfff == 0x297 and lower & 0xfffff == 0x28293, 'Actual HTIF address setup')
        hi = upper & 0xfffff000
        if hi & 0x80000000:
            hi -= 1 << 32
        lo = lower >> 20
        if lo & 0x800:
            lo -= 4096
        need(entry+6+hi+lo == address, 'Actual HTIF AUIPC/ADDI address')
        expected = {entry: 0x0506, entry+2: 0x00156513, entry+6: upper,
                    entry+10: lower, entry+14: 0x0330000f, store_pc: 0x00a2b023}
    for pc, op in expected.items():
        need(elf.insn(pc) == spec['code'][str(pc)] == op, 'Actual backend exit instruction/address path')
    return spec, dict(backend=backend, member=member, address=address, value=value, store_pc=store_pc,
                      store_insn=0x00a2b023, size=8, elf=str(elf_path), elf_sha256=sha(elf_path),
                      spec=str(path), spec_sha256=sha(path), exit_encoding=expected)


class Observer(c.Observer):
    def __init__(self, spec, st, sv, endpoint):
        super().__init__(spec, st, sv)
        self.endpoint = endpoint
        self.exit_events = []

    def record_exit(self, pc, insn, address, value, size):
        e = self.endpoint
        if e['backend'] == 'spike':
            need(address != 0xd0000000, 'CTRL exit forbidden for Spike')
        if pc == e['store_pc'] or address == e['address']:
            need((pc, insn, address, value, size) ==
                 (e['store_pc'], e['store_insn'], e['address'], e['value'], e['size'])
                 and not self.exit_events, 'Exact unique actual backend exit')
            self.exit_events.append(dict(pc=pc, insn=insn, address=address, value=value, size=size))
            self.exit.append((address, value))

    def step(self,pc,insn,gprs,access=(),trap=False,mode=None):
        if pc>=0x80000000:need(self.code.get(pc)==insn,'Actual ELF encoding at '+hex(pc))
        need(pc not in (self.s['trap_entry'],self.s['replay_mismatch'],self.s['mt_bad_trap']),'First error/default trap')
        if pc==self.s['mt_check'] and not trap:
            i=self.calls;need(i<len(self.g)+14,'Extra oracle call')
            if i<len(self.g):v=self.g[i]
            else:
                csr=c.RESTORE[i-len(self.g)];need(csr in self.saved,'Missing saved CSR')
                v=self.saved[csr]&~8 if csr==0x300 else self.saved[csr]
            need(self.regs.get(10)==self.regs.get(11)==v,f'Check{i+1} got={self.regs.get(10)} expected_operand={self.regs.get(11)} gold={v}')
            self.calls+=1
        if pc==self.s['mt_enter']:
            self.initial();self.entered=True
        if pc==self.s['mt_handler']:
            need(len(self.captures)<2,'Extra trap');self.capture={};self.captures.append(self.capture)
            self.actions.append('handler');self.retry=len(self.captures)==1
        if insn&127==0x73:
            f,src,csr,rd=(insn>>12)&7,(insn>>15)&31,insn>>20,(insn>>7)&31
            pure=f in (2,3) and src==0 and rd!=0 and not trap
            if pure:
                need(rd in gprs,'Missing actual CSR result')
                if not self.entered and csr in c.RESTORE:self.saved.setdefault(csr,gprs[rd])
                if self.s['mt_handler']<=pc<self.s['mt_check_ecall'] and csr in c.CSR:
                    need(self.capture is not None and c.CSR[csr] not in self.capture,'CSR capture repetition')
                    self.capture[c.CSR[csr]]=gprs[rd]
            if self.retry and csr==0x341 and f in (1,2,3,5,6,7) and (f in (1,5) or src):
                raise ValueError('Mepc changed before same-PC retry')
        name=self.sites.get(pc)
        if name and not trap:
            self.actions.append(name)
            if mode is not None:
                user_site=name in ('mt_target','mt_result_snapshot','mt_successor_load','mt_successor_store','mt_next_snapshot')
                need(mode==(1 if self.sv and user_site else 3),'Actual site privilege '+name)
            if name=='mt_trap_vstart_read':need(gprs.get(6)==(1 if len(self.captures)==1 else 0),'Fault vstart read')
            if name=='mt_restore_start':need(self.regs.get(6)==1,'Restored original vstart')
            if name=='mt_retry_mret':need(self.retry,'Unpaired retry');self.retry=False
            if name=='mt_target':need(len(self.captures)==1 and not self.retry,'Target not same-PC retry');self.target_success+=1
        for kind,a,v,n in access:
            d=c.memory_op(insn)
            if d is not None:
                need(d['kind']==kind and d['size']==n,'Scalar access kind/size')
                need(d['base'] in self.regs and a==(self.regs[d['base']]+d['offset'])&c.MASK64,'Scalar effective address')
                if kind=='write':
                    src=d['register'];bits=(1<<(8*n))-1
                    if src not in self.regs:
                        # Only compiler entry spills may save opaque caller registers.
                        need(not self.entered and self.s['main']<=pc<self.s['mt_handler'] and
                             d['base']==2 and src in (8,9,*range(18,28)) and n==8,'Unknown source GPR')
                        self.regs[src]=v&bits
                    need(v&bits==self.regs[src]&bits,'Scalar store operand')
            if kind=='write':
                self.write(a,v,n)
                if a in (self.s['mt_errors'],self.s['mt_unexpected']):need(v==0,'Nonzero failure state')
                self.record_exit(pc,insn,a,v,n)
        self.regs.update(gprs);self.regs[0]=0;self.retired+=1

    def finish(self, endpoint):
        need(endpoint == self.endpoint['backend'] and len(self.exit_events) == 1,
             'Complete explicit backend exit')
        result = super().finish(endpoint)
        result.update(endpoint_contract=self.endpoint, actual_exit_events=self.exit_events)
        return result


class Checker(previous.Checker):
    def __init__(self, spec, st, sv, endpoint):
        super().__init__(spec, st, sv)
        self.o = Observer(spec, st, sv, endpoint)


def instance(member, backend='dut'):
    spec, endpoint = bind(member, backend)
    return Checker(spec, member.startswith('store'), member.endswith('sv39'), endpoint)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('member', choices=['load_m', 'store_m', 'load_sv39', 'store_sv39'])
    ap.add_argument('csv', type=Path)
    ap.add_argument('out', type=Path)
    args = ap.parse_args()
    checker = instance(args.member)
    with args.csv.open(newline='') as f:
        reader = csv.DictReader(f)
        need(reader.fieldnames == c.FIELDS, 'CSV schema')
        for row in reader:
            checker.row(row)
    result = checker.finish()
    with args.out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(result['status'])
