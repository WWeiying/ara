"""Offline source/reference audit only; no build, Host or guest execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from collections import Counter

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
F = HERE.parent/'nf2_remaining4_01'
R = F/'reference01'
READY_SHA = 'd427f9c9846e0c59d9374efb6fbae020df08c8f6a4472ce740e05ddf4306aa2f'
IDS = ['u0_s0_b1_m2_f1', 'u1_s1_b3_m2_f0', 'u0_s1_b5_m3_f1', 'u1_s0_b1_m3_f0']


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def read(p): return json.loads(Path(p).read_text())


def save(name, value):
    with (HERE/name).open('x') as f: json.dump(value, f, indent=2); f.write('\n')


def load(p, name):
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def main():
    assert __debug__ and not (HERE/'result.json').exists() and not (HERE/'not_accepted.json').exists()
    begin = time.monotonic()
    try:
        assert sha(F/'READY.json') == READY_SHA
        ready = read(F/'READY.json'); pins = dict(ready['pins'])
        pins[str(F/'READY.json')] = READY_SHA; pins[str(Path(__file__))] = sha(__file__)
        def verify():
            for p, h in pins.items(): assert sha(p) == h, ('pin drift', p)
        verify()
        assert ready['cases'] == IDS and ready['status'] == 'SOURCE_REFERENCE_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT'
        assert ready['VCS_started'] is False and ready['case_count'] == 4
        sys.path.insert(0, str(F))
        ref = load(F/'reference.py', 'sealed_nf2_reference')
        source = ref.provenance()
        assert source == read(F/'source_manifest.json')
        assert [c['id'] for c in source['cases']] == IDS
        assert [(c['base'], c['store'], c['mask'], c['start'], c['unmapped']) for c in ref.CASES] == [
            (4090,0,36,2,0),(4084,1,36,5,1),(4074,1,0,8,0),(4092,0,0,8,1)]
        # Independently derive both fields and all4096 halfwords from original formulas.
        for c, config in enumerate(ref.CASES):
            for phase in ((1,2) if c < 2 else (3,2)):
                mem = [(37*h+11)&65535 for h in range(4096)]
                for i in range(8):
                    if not ((config['mask'] >> i)&1): continue
                    for field in (0,1):
                        h = (config['base']+4*i+2*field)//2
                        if config['store'] and (phase != 1 or i < config['start']): mem[h] = 101+13*i+29*field
                        if phase == 2 and c < 2 and i < config['start']: mem[h] ^= 0x5b
                assert mem == ref.memory_gold(c, phase)
                for field in (0,1):
                    for i in range(64):
                        want = 101+13*i+29*field if config['store'] else 0x5b
                        if not config['store'] and i<8 and ((config['mask']>>i)&1) and (phase!=1 or i<config['start']):
                            want = (37*((config['base']+4*i+2*field)//2)+11)&65535
                        assert ref.vg(c,phase,field+1,i) == want
        # Read ELF bytes directly; never invoke nm/objdump/compiler.
        support = HERE.parents[2]/'merge_original_prefix98_terminal_audit01/support.py'
        assert sha(support) == '4ad5c6b27d60f62e36f406c809bf2aeb4a9f22822e02934f334c3c1a175c52a6'
        pins[str(support)] = sha(support); u = load(support, 'nf2_elf_reader')
        code = {}
        for backend in ('soc','spike'):
            get, syms = u.elf(R/(backend+'.elf'))
            s = read(R/(backend+'.symbols.json'))
            assert all(syms[n][0] == v for n,v in s.items())
            rows = re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+', (R/(backend+'.dis')).read_text(), re.M)
            for pc, encoding in rows:
                assert get(int(pc,16),len(encoding)//2) == bytes.fromhex(encoding)[::-1]
            assert get(s['mx_segment_load'],4) == bytes.fromhex('075c0520')
            assert get(s['mx_segment_store'],4) == bytes.fromhex('275c0520')
            if backend == 'spike': code = {int(pc,16):int(enc,16) for pc,enc in rows}
        s = read(R/'spike.symbols.json')
        attempt, status, host = read(R/'reference_attempt.json'), read(R/'status.json'), read(R/'host.json')
        assert attempt['command'] == [str(ref.base.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu',
            '--pmpregions=0','-m2','--instructions=3000000','-l','--log-commits',str(R/'spike.elf')]
        assert attempt['one_attempt_only'] is True and attempt['bound_sha256'] == sha(R/'bound.json')
        assert status['process_returncode'] == 0 and 0 < status['reference_elapsed_s'] < 120
        assert not (R/'not_completed.json').exists()
        assert host['status'] == 'PASS_HOST_ONLY' and host['oracle_rows'] == 34816
        assert len(host['negative']['rejected']) == 16 and all(x['rejected'] for x in host['negative']['rejected'])
        assert host['negative']['allowed_fault_segment_snapshot'] is True
        observed = dict(records=0, firmware_records=0, checks=0, lines=0)
        regs = {i:0 for i in range(32)}; captures=[]; retries=[]; vstart_writes=[]; csr_reads=[]
        excluded = Counter(); unexpected=[]; boot=[]; targets=[]
        pattern = re.compile(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$')
        class Trace(str):
            def splitlines(self):
                for line in super().splitlines():
                    observed['lines'] += 1
                    m = pattern.match(line)
                    if not m:
                        if re.match(r'^core\s+0:\s+0x',line): excluded['disassembly']+=1
                        elif re.match(r'^core\s+0:\s+>>>>',line): excluded['symbols']+=1
                        elif re.match(r'^core\s+0:\s+(?:exception|tval)',line): excluded['exception_metadata']+=1
                        elif not line.strip(): excluded['blank']+=1
                        else:
                            excluded['other']+=1
                            if len(unexpected)<10: unexpected.append(line)
                        yield line; continue
                    mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4]
                    observed['records']+=1
                    if pc < 0x80000000: boot.append([pc,insn])
                    else:
                        assert code.get(pc) == insn, ('actual PC/code',hex(pc),hex(insn))
                        observed['firmware_records']+=1
                    assert pc not in (s['trap_entry'], s['replay_mismatch'])
                    if pc == s['check']:
                        assert regs[10] == regs[11], ('first firmware mismatch',observed['checks'],regs[10],regs[11])
                        observed['checks']+=1
                    if pc == s['mx_handler']: captures.append({})
                    updates = {int(n):int(v,16) for n,v in re.findall(r'\bx(\d+)\s+0x([0-9a-f]+)',tail)}
                    if insn&127 == 0x73 and (insn>>12)&7:
                        csr,funct,rs,rd=insn>>20,(insn>>12)&7,(insn>>15)&31,(insn>>7)&31
                        if funct in (2,3) and rs==0 and rd:
                            value=updates.get(rd)
                            csr_reads.append(dict(pc=hex(pc),csr=csr,value=value))
                            if s['mx_trap']<=pc<s['main'] and captures and csr in (0x342,0x341,0x343,0xc20,0xc21,8,3,15):
                                assert csr not in captures[-1]
                                captures[-1][csr]=value
                        writing=funct in (1,5) or rs!=0
                        if writing and csr==8: vstart_writes.append(rs if funct>=5 else regs[rs])
                        if writing and csr==0x341 and captures and captures[-1].get(0x342) in (13,15):
                            raise AssertionError('Fault mepc overwritten before retry')
                    if pc == s['mx_trap_mret'] and captures[-1].get(0x342) in (13,15):
                        expected=2 if len(retries)==0 else 5
                        assert len(retries)<2 and vstart_writes[-1] == expected
                        assert captures[-1][8] == expected
                        retries.append(dict(start=expected,pc=hex(captures[-1][0x341]),record=observed['records']))
                    if pc in (s['mx_segment_load'],s['mx_segment_store']):
                        targets.append(dict(pc=hex(pc),mode=mode,record=observed['records']))
                    regs.update(updates); regs[0]=0
                    yield line
        raw = Trace((R/'spike.trace').read_text())
        rebuilt = ref.validate(raw,s)
        assert not unexpected, ('Unclassified raw lines',unexpected)
        assert boot == [[0x1000,0x297],[0x1004,0x02028593],[0x1008,0xf1402573],[0x100c,0x0182b283],[0x1010,0x28067]]
        assert observed['records'] == rebuilt['commits'] == 1315037 and observed['checks'] == rebuilt['checks'] == 3567
        assert len(captures)==6 and [c[0x342] for c in captures] == [13,9,15,9,9,9]
        assert len(retries)==2 and len(targets)==6
        for k,v in rebuilt.items(): assert json.loads(json.dumps(v)) == status[k], ('Producer report differs',k)
        assert sha(R/'spike.trace') == status['raw_sha256'] and len(raw.encode()) == status['raw_bytes']
        verify()
        save('verified_pins.json',pins)
        save('result.json',dict(status='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT',ready_sha256=READY_SHA,
            cases=IDS,pins_verified=len(pins),pins_pre_post_unchanged=True,rebuilt=rebuilt,
            observer=observed,raw_noncommit_line_classes=dict(excluded),raw_unknown_lines=unexpected,
            trap_CSR_reads=captures,retries=retries,target_records=targets,csr_reads=csr_reads,
            host_rerun=False,Spike_rerun=False,DUT_executed=False,reference_full_parses=1,
            original_Linux_ELF_executed=False,original_mask_bytes=128,fixture_mask_bytes=16,consumed_mask_bytes=8,
            protected_vs_unmapped_PTE_both_invalid=True,linux_signal_frame_proved=False,
            audit_seconds=time.monotonic()-begin))
        print('ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT',sha(HERE/'result.json'),flush=True)
    except BaseException as error:
        save('not_accepted.json',dict(status='NOT_ACCEPTED',firstcause=repr(error),audit_seconds=time.monotonic()-begin))
        raise


if __name__ == '__main__': main()
