"""Bounded HTIF probe: prove unsupported custom ISA, never a QBS PASS."""
import json
import re
from pathlib import Path

import build_gap38_i8_f16_lane3 as common


def check(trace, symbols):
    traps = re.findall(r'exception trap_illegal_instruction, epc (0x[0-9a-fA-F]+)', trace)
    expected_pc = [symbols['probe_info'], symbols['probe_exec']]
    common.require([int(pc,16) for pc in traps] == expected_pc, 'precise unsupported opcode PCs differ')
    stores = {int(a,16): int(v,16) for a,v in
              re.findall(r'\bmem (0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)', trace)}
    base = symbols['probe_ledger']
    expected = [2,0x0005155b,expected_pc[0],2,0x0eb5045b,expected_pc[1]]
    common.require([stores.get(base+8*i) for i in range(6)] == expected,
                   'precise capability ledger differs')
    common.require(stores.get(symbols['tohost']) == 1, 'capability probe did not complete')
    return dict(status='QBS_CUSTOM_ISA_UNSUPPORTED_NOT_FUNCTIONAL_PASS',
                exception_pcs=expected_pc,ledger=expected,custom_isa_pass=False,
                qbs_app_spike_executed=False,capability_probe_completed=True)


def probe(b, spike):
    source = Path(__file__).with_name('gap105_spike_capability_probe.S')
    b.bind_sources([Path(__file__), source])
    obj = b.compile(source,'spike-capability')
    elf = b.out/'spike-capability.elf'
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles',f'-T{b.common/"link.ld"}',
            obj,'-o',elf],'spike-capability.link')
    raw = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--symbols',elf],
                'spike-capability.metadata')
    symbols = {r['Symbol']['Name']['Name']:r['Symbol']['Value']
               for r in json.loads(raw.stdout)[0]['Symbols']}
    cmd = [str(spike),'--isa=rv64gcv_zfh_zvfh_zvl1024b','-l','--log-commits',str(elf)]
    run = b.run(cmd,'spike-capability',timeout=10)
    trace_path = b.out/'spike-capability.stderr.log'
    result = check(trace_path.read_text(),symbols)
    result.update(command=cmd,timeout_s=10,returncode=run.returncode,
                  elf=str(elf),elf_sha256=common.sha(elf),trace=str(trace_path),
                  trace_sha256=common.sha(trace_path))
    common.save(b.out/'spike-preflight.json',result)
    return result
