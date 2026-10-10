"""One source, three Spike preflights; handoff to shared external-reset owner."""
import argparse
import json
from pathlib import Path
import subprocess
from elftools.elf.elffile import ELFFile
import prepare_fpu_half_reset744 as half

life, require, old = half.life, half.require, half.old
APP = life.ROOT / 'apps/riscv-tests/isa/rv64uv/vgap_fpu_active_reset_matrix.c'
PRE = life.OUT / 'fpu-active-reset-matrix-preflight745-agent-20261007-01'
BASE = life.OUT / 'gap115-offline-admitted-745-agent-20261007-01'
STAGES = {'RF': (4, 12), 'EX1': (5, 7), 'EX2': (6, 8), 'WB_REQ': (7, 15)}
GOLD = {16: (0x3c003c003c003c00, 0x4200420042004200, 0x3555355535553555),
        32: (0x3f8000003f800000, 0x4040000040400000, 0x3eaaaaaa3eaaaaaa),
        64: (0x3ff0000000000000, 0x4008000000000000, 0x3fd5555555555555)}


def oracle(value, sew):
    require(sew in GOLD, 'Invalid SEW')
    require([value('g75_result', 0, 4), value('g75_result', 4, 4), value('num_failed', 0, 4),
             value('tohost')] == [679, 0, 0, 1], 'Terminal/check count')
    for i in range(512):
        gold = 0x123456789abcdef0 if i < 128 else GOLD[sew][i//128-1]
        require(value('fpar_vrf', 8*i) == gold, 'Full VRF differs')
    require([value('fpar_csr', 8*i) for i in range(5)] == [8192//sew, {16:11,32:19,64:27}[sew], 0, 0, 33],
            'CSR/RTZ/NX differs')


def build():
    require(not PRE.exists(), 'Fresh three-ELF preparation only')
    prior = json.loads((old.PRE / 'preflight.json').read_bytes()); life.check(prior['pins'])
    pins = dict(prior['pins'])
    for p in (APP, Path(__file__).resolve(), Path(__file__).with_name('test_prepare_fpu_reset_matrix.py'),
              Path(half.__file__).resolve(), BASE/'admission-manifest.json', BASE/'combined-bits.json'):
        pins[str(p)] = life.digest(p)
    book=json.loads((BASE/'admission-manifest.json').read_bytes())
    bits=life.read_bound(BASE/'combined-bits.json',book['output_pins'][str(BASE/'combined-bits.json')])
    require(len(bits['tests'])==len(set(bits['tests']))==745,'Not exact745')
    source_pins = json.loads((old.shared.reviewed.base.capture.BUILD/'build-source-pins.json').read_bytes())
    for rel in ('hardware/tb/ara_tb.sv','hardware/src/lane/vmfpu.sv','hardware/include/ara_pkg.sv',
                'hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv',
                'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_ctrl.v'):
        p=life.ROOT/rel; pins[str(p)]=source_pins[str(p)]
    life.check(pins); PRE.mkdir(); cases=[]
    original=json.loads((old.PRE/'compile-command.json').read_bytes())
    spike=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    pins[str(spike)]=life.digest(spike)
    for sew in GOLD:
        out=PRE/('sew%d'%sew);out.mkdir()
        cmd=[str(APP) if x==str(old.APP) else str(out/'input.elf') if x==str(old.PRE/'input.elf') else x for x in original]
        cmd.insert(1,'-DFPAR_SEW=%d'%sew); require('-O2' in cmd and 'ZCC' not in ' '.join(cmd),'Compiler contract')
        life.save(out/'compile-command.json',cmd)
        with (out/'build.log').open('x') as log: subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        symbols={k:old.shared.template.s._elf_symbol(out/'input.elf',old.shared.template.s.LLVM/'llvm-readelf',k) for k in half.SYMBOLS}
        sc=[str(spike),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(out/'input.elf')]
        life.save(out/'spike-command.json',sc)
        with (out/'spike.trace').open('x') as log: subprocess.run(sc,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        commits=old.shared.shared.spike_trace.parse_spike_commits(out/'spike.trace')
        writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
        oracle(lambda n,o=0,size=8:writes.get(symbols[n]+o),sew)
        require(not any(c.pc==symbols['trap_fail'] for c in commits),'Spike trap')
        require('exception ' not in (out/'spike.trace').read_text(),'Spike exception')
        early=[c for c in commits if c.pc < symbols['fpar_first_ar_load'] and c.pc>=symbols['fpar_mul']]
        require(not any(c.instruction & 127 in (7,39) for c in commits
                        if 0x80000000<=c.pc<symbols['fpar_first_ar_load']), 'Unexpected vector memory before trigger')
        with (out/'input.elf').open('rb') as stream: segments=[(s['p_vaddr'],s.data()) for s in ELFFile(stream).iter_segments() if s['p_type']=='PT_LOAD']
        source=[data[symbols['source']-a:symbols['source']-a+1280] for a,data in segments if a<=symbols['source'] and symbols['source']+1280<=a+len(data)]
        gold=b''.join(v.to_bytes(8,'little') for v in [0x5a3c719de4b208f6]*16+[0x123456789abcdef0]*128+[0x5a3c719de4b208f6]*16)
        require(source==[gold],'ELF source guards differ')
        row=dict(sew=sew,symbols=symbols,counts=old.shared.shared.reference_counts(commits,symbols),ELF=str(out/'input.elf'),
                 ELF_sha256=life.digest(out/'input.elf'),spike_trace=str(out/'spike.trace'),gold=GOLD[sew],
                 active_cores={16:16,32:8,64:4}[sew])
        for p in out.iterdir(): pins[str(p)]=life.digest(p)
        cases.append(row)
    targets=[]
    for scope,row in bits['metrics']['fsm'].items():
        if '.i_ara.gen_lanes[' in scope and scope.endswith('.i_ct_vfdsu_top.x_ct_vfdsu_ctrl'):
            require(row['width']==17,'C910 controller shape')
            require(all(not int(row['bits'],16)&(1<<(16-i)) for _,i in STAGES.values()),'Target already hit745')
            targets.append(dict(scope=scope,state_signal=scope+'.div_cur_state',raw_bitmap=row,
                                stage_to_reset_raw_indices={s:i for s,(_,i) in STAGES.items()}))
    require(len(targets)==16,'Exact16 vector C910 controllers')
    life.check(pins)
    record=dict(status='THREE_SPIKE679_PASS_NATIVE_RESET_NOT_EXECUTED',cases=cases,pins=pins,
                stages=STAGES,targets=targets,baseline=745,timeout_s=600,no_internal_force=True,reset_full_clocks=4,
                EDA_launched=False,coverage_admitted=False,
                timing='State-conditioned stop/get at actual C910 controller; no NOP latency assumption used for stage targeting.',
                control='Only ara_tb.rst_n deposits0/1; stage read-only; no TB RESET_ON_AXI argument in stage runs.',
                execution_owner='Descartes shared externalTBreset helper; this fixture tool has no run entry.',
                evidence_boundary='Actual state/Get/pin deposition and VPD are required from shared runner; no predicted stage gain claimed.',
                qualification='Capture actual stage/reset for every core from focused VPD; independent twoepoch lifecycle/scalar/vector and AR/R; no guarantee that reset arcs are sampled.')
    life.save(PRE/'preflight.json',record)
    print(json.dumps(dict(output=str(PRE),seal=life.digest(PRE/'preflight.json'),counts=[r['counts'] for r in cases])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',action='store_true',required=True)
    p.parse_args();build()
