"""Bounded Sv39 matrix build/Spike oracle and conditional raw768 Toggle prediction."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import run_gap95_simulation as life
import build_gap98_preflight as build
import collect_gap103_strict as architecture
import targeted_toggle_evidence_v2 as native

ROOT, OUT, require = life.ROOT, life.OUT, build.require
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vtlb_asid_vpn_rsw_matrix.c'
RANK = OUT/'cva6-toggle-capacity-source-review768-agent-20261007-01.json'
RANK_SHA = 'd964f780dd7ecfbfa928c72b77bb42e2fe0e41e90830dfad84ff377909862f08'
CACHE = OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'
BASE = OUT/'stride-metadata-full64-offline-admitted-768-agent-20261007-01'
TEMPLATE = OUT/'gap99-csr-satp-mprv-preflight-707-20261006-01/compile-command.json'
SOURCE = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
SOURCE_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_dtlb'
GOLD, GUARD = 0x9ac571e23db8046f, 0x5a3c719de4b208f6
SYMBOLS = ('tohost','num_failed','g75_result','trap_fail','tam_observed','tam_csr',
           'tam_data','tam_root','tam_mid','tam_leaf','tam_first_load','tam_second_load')


def vpn(phase, entry):
    value = (0x5555555 ^ (entry * 0x111111)) & 0x7ffffff
    return value ^ 0x7ffffff if phase == 1 else value


def address(phase, entry):
    value = vpn(phase, entry) << 12
    return (value | (((1 << 64) - (1 << 39)) if value & (1 << 38) else 0)) | 8


def plru_order():
    tree = [0] * 15
    phases = []
    for _ in range(3):
        order = []
        for _ in range(16):
            victims = [i for i in range(16) if all(
                tree[(1 << level)-1 + (i >> (4-level))] == ((i >> (3-level)) & 1)
                for level in range(4))]
            require(len(victims) == 1, 'Ambiguous PLRU victim')
            i = victims[0]; order.append(i)
            # Two completed loads to the same entry: both hits select the same path.
            for _ in range(2):
                for level in range(4):
                    tree[(1 << level)-1+(i >> (4-level))] = 1-((i >> (3-level)) & 1)
        require(set(order) == set(range(16)), 'Phase did not visit all entries')
        phases.append(order)
    require(phases[0] == phases[1] == phases[2], 'VPN complement entry alignment differs')
    return phases


def validate(commits, symbols):
    require(not any(c.vector_writes or c.pc == symbols['trap_fail'] for c in commits), 'Unexpected vector/trap')
    writes = {a:v for c in commits for a,v in c.memory_accesses if v is not None}
    require([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
             writes.get(symbols['num_failed']),writes.get(symbols['tohost'])] == [107,0,0,1],
            'Complete107-check terminal differs')
    original = writes.get(symbols['tam_csr'])
    require(original is not None, 'Original mstatus missing')
    csr = [original,0] + [(8 << 60) | ((65535 if p != 1 else 0) << 44) |
                         (symbols['tam_root'] >> 12) for p in range(3)] + [original]*3 + [0]
    require([writes.get(symbols['tam_csr']+8*i) for i in range(9)] == csr, 'CSR restoration/phase differs')
    require([writes.get(symbols['tam_observed']+8*i) for i in range(96)] == [GOLD]*96,
            'Independent96 load results differ')
    loads = [c for c in commits if c.pc in (symbols['tam_first_load'],symbols['tam_second_load'])]
    require(len(loads) == 96, 'Missing/extra target load')
    for index,c in enumerate(loads):
        phase,entry = index//32,(index%32)//2
        require(c.pc == symbols['tam_first_load' if index%2 == 0 else 'tam_second_load'] and
                is_ld_zero(c.instruction) and list(c.gpr_writes.values()) == [GOLD] and
                tuple(c.memory_accesses) == ((address(phase,entry),None),), 'Exact target PC/address/value differs')
    pte = lambda a,f: ((a >> 12) << 10) | f
    expected = {symbols['tam_root']+16:pte(0x80000000,0xcf)}
    for phase in range(2):
        for entry in range(16):
            v = vpn(phase,entry)
            expected[symbols['tam_root']+8*(v >> 18)] = pte(symbols['tam_mid'],1)
            expected[symbols['tam_mid']+8*((v >> 9)&511)] = pte(symbols['tam_leaf'],1)
    for entry in range(16):
        expected[symbols['tam_leaf']+8*(vpn(2,entry)&511)] = pte(symbols['tam_data'],0xc7)
    for name in ('tam_root','tam_mid','tam_leaf'):
        require(symbols[name]%4096 == 0, 'Page table misaligned')
        for i in range(512):
            a = symbols[name]+8*i
            require(writes.get(a) == expected.get(a,0), 'Full independent PTE image differs')
    for i in range(16):
        a = symbols['tam_leaf']+8*(vpn(0,i)&511)
        history = [v for c in commits for p,v in c.memory_accesses if p == a and v is not None]
        require(history[-3:] == [pte(symbols['tam_data'],f) for f in (0xc7,0x3c7,0xc7)],
                'Exact RSW0/3/0 phase PTE writes differ')
    require(not any(symbols['tam_data'] <= a < symbols['tam_data']+24 or
                    0xd0000000 <= a < 0xd0001000 for a in writes), 'Data/guard/MMIO write')
    guard_reads = [c for c in commits if any(a in (symbols['tam_data'],symbols['tam_data']+16)
                                          for a,v in c.memory_accesses if v is None)]
    require(len(guard_reads) == 2 and all(list(c.gpr_writes.values()) == [GUARD] for c in guard_reads),
            'Guard observations differ')
    return architecture.reference_counts(commits,symbols)


def is_ld_zero(word):
    if word & 3 == 3:
        return word & 0x707f == 0x3003 and word >> 20 == 0
    # RV64 C.LD (quadrant0, funct3=011): immediate uimm[7:6|5:3].
    return word & 0xe003 == 0x6000 and word & 0x1c60 == 0


def source_contract(texts):
    clean = lambda s: re.sub(r'\s+','',re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S))
    tlb,mmu,cfg = (clean(texts[n]) for n in ('cva6_tlb.sv','cva6_mmu.sv','cv64a6_imafdcv_sv39_config_pkg.sv'))
    require('DataTlbEntries:int\'(16)' in cfg and 'UseSharedTlb:bit\'(0)' in cfg and
            'localparamCVA6ConfigHExtEn=0;' in cfg, 'Frozen16/RVH0/shared-disabled config differs')
    require('assigndtlb_lu_access=lsu_req_i&!misaligned_ex_i.valid;' in mmu and
            '.TLB_ENTRIES(CVA6Cfg.DataTlbEntries)' in mmu, 'DTLB access/config differs')
    for token in ('if(lu_hit[i]&lu_access_i)', 'idx_base=$unsigned((2**lvl)-1);',
                  'shift=$clog2(TLB_ENTRIES)-lvl;', 'new_index=~((i>>(shift-1))&32\'b1);',
                  'plru_tree_n[idx_base+(i>>shift)]=new_index[0];',
                  "plru_tree_q<='{default:0};",'elseif(update_i.valid&replace_en[i]&!lu_hit_o)',
                  'content_n[i].pte=update_i.content;',
                  "if(asid_to_be_flushed_is0&&vaddr_to_be_flushed_is0)tags_n[i].valid=1'b0;"):
        require(token in tlb,'Frozen PLRU/update/flush semantics differ: '+token)
    require('plru_tree_n=plru_tree_q;' in tlb, 'PLRU hold differs')
    return dict(entries=16,RVH=0,shared_tlb=0,flush='SFENCE invalidates tags, does not reset PLRU',
                model=plru_order(),boundary='prediction conditional on same-entry repeated hits; no claimed measured gain')


def prediction():
    rank = life.read_bound(RANK,RANK_SHA)
    base_path = BASE/'admission-manifest.json'
    base = life.read_bound(base_path,rank['pins'][str(base_path)])
    ledger_path = BASE/'combined-inputs.txt'
    require(life.digest(ledger_path) == rank['pins'][str(ledger_path)], 'Formal768 ledger drift')
    ledger = ledger_path.read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 769, 'Exact768 ledger required')
    cache = life.read_bound(CACHE,CACHE_SHA)
    old_path = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(life.digest(old_path) == cache['input_pins'][str(old_path)] and
            ledger[:742] == old_path.read_text().splitlines(), 'Exact741 cached prefix differs')
    pins = {str(RANK):RANK_SHA,str(CACHE):CACHE_SHA,str(base_path):rank['pins'][str(base_path)],
            str(ledger_path):rank['pins'][str(ledger_path)],str(old_path):cache['input_pins'][str(old_path)]}
    merged = {SCOPE:cache['instances'][SCOPE]}
    for vdb in ledger[742:]:
        files = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Ambiguous suffix Toggle data')
        path = files[0]; sha = base['input_pins'][str(path)]
        sample,actual = native.rows(path,[SCOPE]);require(actual == sha,'Suffix data drift')
        pins[str(path)] = sha;merged = native.union(merged,sample)
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    for p in paths: pins[str(p)] = rank['pins'][str(p)]
    life.check(pins)
    checks,defs = native.definitions(*(native.xml(p) for p in paths),[SCOPE])
    require(checks[SCOPE] == '817233724' and defs[SCOPE]['module']['chksum'] == '475068782' and
            merged[SCOPE]['width'] == 11852, 'Compiled DTLB identity differs')
    bits = format(int(merged[SCOPE]['bits'],16),'011852b'); offset = 0; targets = []
    for n in ET.fromstring(defs[SCOPE]['shape']).find('tglshape'):
        if n.tag not in ('node','vectornode'): continue
        width = 1 if n.tag == 'node' else abs(int(n.get('left'))-int(n.get('right')))+1
        if re.fullmatch(r'(?:tags_[qn]\[\d+\]\.(?:asid|vpn\[\d+\])|content_[qn]\[\d+\]\.pte\.rsw)',n.get('name','')):
            positions = list(range(offset,offset+2*width))
            targets.append(dict(native=dict(n.attrib),kind=n.tag,serialized_positions=positions,
                                fresh_positions=[i for i in positions if bits[i] == '0']))
        offset += 2*width
    require(offset == 11852 and targets, 'Typed serialization/targets differ')
    return dict(scope=SCOPE,checksum=checks[SCOPE],width=11852,targets=targets,
                conditional_fresh_positions=sum(len(t['fresh_positions']) for t in targets),
                plru_entry_order=plru_order(), measured_gain=None, official_percentage=False,
                condition='16 updates per phase; two loads hit each entry; no unrelated matching accesses; native VCS measurement required',
                contrast='742/762 used ASID0 and two adjacent VPNs; this uses 16 widely spaced/complemented VPNs, ASIDffff/0/ffff, RSW0/3/0'),pins


def prepare(output):
    require(not output.exists(), 'Fresh preflight required')
    pred,pins = prediction()
    require(pred['conditional_fresh_positions'] >= 300, 'Insufficient predicted fresh capacity')
    book = life.read_bound(SOURCE,SOURCE_SHA)
    pins[str(SOURCE)] = SOURCE_SHA
    texts = {}
    for rel in ('core/cva6_mmu/cva6_tlb.sv','core/cva6_mmu/cva6_mmu.sv','core/load_store_unit.sv',
                'core/include/build_config_pkg.sv','core/include/cv64a6_imafdcv_sv39_config_pkg.sv'):
        p = ROOT/'hardware/deps/cva6'/rel;pins[str(p)] = book[str(p)]
        require(life.digest(p) == pins[str(p)],'Historical source mismatch');texts[p.name] = p.read_text()
    source_proof = source_contract(texts)
    command = json.loads(TEMPLATE.read_bytes())
    old = str(ROOT/'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    require(command.count(old) == 1,'Known scalar template required')
    command = [str(APP) if s == old else str(output/'input.elf') if s.endswith('/input.elf') else s for s in command]
    for p in (APP,TEMPLATE,Path(__file__).resolve(),Path(__file__).with_name('test_build_tlb_asid_matrix.py'),
              ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',
              Path(command[0]),build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',build.SPIKE,
              Path(life.__file__),Path(build.__file__),Path(architecture.__file__),Path(native.__file__),Path(native.base.__file__)):
        pins[str(p)] = life.digest(p)
    for directory in ('apps/riscv-tests/isa/macros','apps/riscv-tests/env','apps/common'):
        for p in (ROOT/directory).rglob('*'):
            if p.is_file():pins[str(p)] = life.digest(p)
    life.check(pins);output.mkdir();life.save(output/'input-pins.json',pins)
    try:
        life.save(output/'prediction.json',pred);life.save(output/'source-contract.json',source_proof)
        life.save(output/'compile-command.json',command)
        with (output/'build.log').open('x') as f:
            subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=120,check=True)
        symbols = {n:build._elf_symbol(output/'input.elf',build.LLVM/'llvm-readelf',n) for n in SYMBOLS}
        spike = [str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                 '-m0x80000000:0x20000000','-l','--log-commits',str(output/'input.elf')]
        life.save(output/'spike-command.json',spike)
        with (output/'spike.trace').open('x') as f:
            subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,timeout=120,check=True)
        require('exception ' not in (output/'spike.trace').read_text(),'Unexpected Spike exception')
        counts = validate(build.parse_spike_commits(output/'spike.trace'),symbols)
        life.check(pins)
        pins = life.merge_pins(pins,{str(p):life.digest(p) for p in output.iterdir() if p.is_file()})
        life.save(output/'preflight.json',dict(status='SPIKE107_CHECKS_AND_INDEPENDENT_PTE_CSR_GUARDS_PASS_NOT_RTL',
            input_pins=pins,symbols=symbols,counts=counts,software_checks=107,baseline=768,
            prediction=pred,coverage_admitted=False,VCS_launched=False))
        print('PREFLIGHT_PASS '+life.digest(output/'preflight.json'),flush=True)
    except Exception as e:
        life.save(output/'failure.json',dict(reason=str(e),coverage_admitted=False));raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output.absolute())
