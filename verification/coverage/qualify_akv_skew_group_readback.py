"""Exact historical skew architectural readbacks; no VCS, admission or full-ISA claim."""
import argparse
from bisect import bisect_right
import csv
import json
from pathlib import Path
import struct

import audit_akv_budget_qualification_gaps as inventory
import akv_historical_budget_source_proof_717 as source
import collect_opivx_vsbc_strict as memory

old, require = inventory.old, inventory.old.require
RUN = inventory.RUNS[old.SKEW]
OUT = inventory.OUT
ELF_SHA = 'bb333b09bee3df3280dff94abb0aedb257c8c7ae434396c7c5b604d470ab0051'


def halfwords(values):
    return b''.join(struct.pack('<H',v&65535) for v in values)


def expected_regions(phase, symbols):
    require(type(phase) is int and 0 <= phase < 12,'Invalid phase')
    seed = [0x9000+phase*256+i*13 for i in range(256)]
    before,after = halfwords(0xc100+i for i in range(32)),halfwords(0xd200+i for i in range(32))
    initial = before+halfwords(seed)+after
    data = list(seed)
    if phase in (1,2,3,8,9,10):
        stream = (phase-1) if phase < 4 else phase-8
        epoch = int(phase >= 8)
        data[:64] = [0x1100+epoch*0x1000+stream*0x2000+i*7 for i in range(64)]
    external, descriptors = bytearray(),bytearray()
    for epoch in range(2):
        starts = [64,64,64] if epoch else [66,70,78]
        for stream,start in enumerate(starts):
            poisoned = phase >= (8 if epoch else 1)
            for b in range(256):
                if start <= b < start+128:
                    d = b-start
                    value = 0x1100+epoch*0x1000+stream*0x2000+(d//2)*7
                    if poisoned: value ^= 0x5a5a
                    external.append((value >> ((d&1)*8))&255)
                else:
                    external.append((0xa7+epoch*19+stream*29+b*11)&255)
        stride = 128 if epoch else 130
        base = symbols['source']['value']+epoch*768
        descriptors.extend(struct.pack('<4B2H4I5Q',1,1,1,0,64,1,stride,stride,stride,0,
                                       base+starts[0],base+256+starts[1],base+512+starts[2],0,0))
    return {'got':before+halfwords(data)+after,'initial':initial,'source':bytes(external),
            'descriptor':bytes(descriptors),'descriptor_copy':bytes(descriptors)}


def audit_readbacks(rows, symbols, command_cycles):
    require(len(command_cycles) == 12 and command_cycles == sorted(set(command_cycles)), 'Exact12 command windows required')
    expected = [expected_regions(p,symbols) for p in range(12)]
    seen = [{name:set() for name in expected[p]} for p in range(12)]
    reads = [0]*12
    ranges = [(symbols[name]['value'],symbols[name]['value']+len(blob),name)
              for name,blob in expected[0].items()]
    for r in rows:
        if r['event'] != 'retire' or not int(r['mem_rmask'],16): continue
        address = int(r['mem_addr'],16)
        owners = [(lo,hi,name) for lo,hi,name in ranges if lo <= address < hi]
        if not owners: continue
        phase = bisect_right(command_cycles,int(r['cycle']))-1
        # setup may inspect its own bytes before the first command; not a
        # post-command observation and not counted toward any phase proof.
        if phase < 0: continue
        require(len(owners) == 1,'Aliased architectural regions')
        lo,hi,name = owners[0]
        access = memory.scalar_memory(int(r['insn'],16))
        require(access is not None and access[0] == 'read','Unrecognized region load')
        width = access[1]
        require(int(r['rd']) != 0 and not int(r['trap']) and address+width <= hi and
                address%width == 0 and int(r['mem_wmask'],16) == 0 and
                int(r['mem_rmask'],16) == ((1<<width)-1)<<(address&7), 'Unobservable/malformed region load')
        offset = address-lo
        got = (int(r['rd_wdata'],16)&((1<<(width*8))-1)).to_bytes(width,'little')
        require(got == expected[phase][name][offset:offset+width],
                'Independent bytes mismatch phase=%d region=%s offset=%d pc=%s' % (phase,name,offset,r['pc']))
        seen[phase][name].update(range(offset,offset+width));reads[phase] += 1
    for phase in range(12):
        for name,blob in expected[phase].items():
            require(seen[phase][name] == set(range(len(blob))),
                    'Incomplete explicit readback phase=%d region=%s missing=%d' %
                    (phase,name,len(set(range(len(blob)))-seen[phase][name])))
    return dict(status='SKEW_ALL12_PHASE_ARCHITECTURAL_BYTES_AND_GUARDS_PASS',
        phases=12,per_phase_bytes={name:len(blob) for name,blob in expected[0].items()},
        total_independent_unique_phase_bytes=sum(len(blob) for blob in expected[0].values())*12,
        destination_frame_bytes=7680,destination_active_and_tail_bytes=6144,destination_guard_bytes=1536,
        seed_frame_bytes=7680,external_source_and_guard_bytes=18432,descriptor_and_copy_bytes=3072,
        explicit_scalar_loads_by_phase=reads,skipped_region_reads=0,
        frozen_context_not_live_poison_verified=True,illegal_phases=[4,5,6],
        golden_inputs='Only phase/static formulas and ELF symbol addresses, never observed DUT data',
        scope='Complete original v8..v11 group/tails and all original software guard regions; not full32VRF or vector write-port proof')


def collect(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(),'Fresh sidecar directory required')
    manifest = json.loads((RUN/'manifest.json').read_text())
    sealed = json.loads((RUN/'result-seal.json').read_text())
    pins = dict(sealed)
    for path,h in manifest['pins'].items():
        require(inventory.digest(path) == h,'Original source/input pin drift: '+path)
        require(path not in pins or pins[path] == h,'Conflicting original result pin')
        pins[path] = h
    blob = (RUN/'input.elf').read_bytes()
    require(inventory.digest(RUN/'input.elf') == manifest['elf_sha256'] == ELF_SHA,'Foreign ELF')
    terminal = json.loads((RUN/'terminal.json').read_text())
    require(terminal['status'] == 'FULL_ORIGINAL_ORACLE_PASS_NOT_ADMITTED' and
            terminal['returncode'] == 0 and terminal['coverage_admitted'] is False,'Failed historical run')
    for p,h in pins.items(): require(inventory.digest(p) == h,'Original result drift: '+p)
    # Reuse the reviewed original protocol/CSR/PERF validator including its
    # source-qualified bare translation gate, without mutating frozen code.
    original = source.verify(old.SKEW,RUN,blob,2097152)
    require(original == json.loads((RUN/'oracle-result.json').read_text()),'Original runtime proof differs')
    symbols = original['elf_layout']['symbols']
    cycles = [c['request_cycle'] for c in original['protocol']['custom']]
    with (RUN/'commit_trace.csv').open() as stream:
        proof = audit_readbacks(csv.DictReader(stream),symbols,cycles)
    for path in [RUN/'result-seal.json',RUN/'manifest.json',Path(__file__).resolve(),
                 Path(__file__).with_name('test_qualify_akv_skew_group_readback.py'),
                 Path(inventory.__file__).resolve(),Path(old.__file__).resolve(),
                 Path(source.__file__).resolve(),Path(memory.__file__).resolve()]:
        pins[str(path)] = inventory.digest(path)
    for p,h in pins.items(): require(inventory.digest(p) == h,'Final input drift: '+p)
    out.mkdir()
    values = {'independent-readback.json':proof,'reused-runtime-proof.json':original,
        'status.json':dict(status='SKEW_NATIVE_ARCHITECTURAL_READBACK_QUALIFIED_NOT_ADMITTED',
            run=str(RUN),elf_sha256=ELF_SHA,image_files=66,checks=3237,exceptions=3,
            actual_immediate_fflags_vstart_reads=24,phases=12,
            original_group_and_guards_independent_qualified=True,full_scalar_independent_qualified=False,
            full_scalar_differential_qualified=False,native_Spike_comparison=False,
            all32_VRF_qualified=False,native_vector_write_ports_qualified=False,
            coverage_admitted=False,raw_union_computed=False,rtl_changed=False,simulations_started=False)}
    for name,value in values.items():
        with (out/name).open('x') as stream: json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
    seal = dict(input_pins=pins,output_pins={str(out/name):inventory.digest(out/name) for name in values},
                status=values['status.json']['status'],coverage_admitted=False)
    with (out/'qualification-seal.json').open('x') as stream:
        json.dump(seal,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(output=str(out),seal=inventory.digest(out/'qualification-seal.json'),
                         pins=len(pins),proof=proof,status=seal['status'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('collect','verify'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal');args = parser.parse_args();out = args.output.absolute()
    if args.mode == 'collect':
        require(args.seal is None,'No guessed seal for collect');collect(out)
    else:
        require(args.seal and inventory.digest(out/'qualification-seal.json') == args.seal,'Wrong sidecar seal')
        seal = json.loads((out/'qualification-seal.json').read_text())
        for p,h in {**seal['input_pins'],**seal['output_pins']}.items():
            require(inventory.digest(p) == h,'Sidecar pin drift: '+p)
        print('VERIFY_PASS SKEW_ARCHITECTURAL_READBACK_NOT_ADMITTED')


if __name__ == '__main__': main()
