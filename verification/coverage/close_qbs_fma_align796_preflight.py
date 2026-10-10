"""Close the completed03 Spike capture with ELF-bound snapshot stride only."""
import argparse
import json
from pathlib import Path
from types import FunctionType
from elftools.elf.elffile import ELFFile

import preflight_qbs_fma_align795 as old

CAPTURE = old.OUT/'qbs-fma-align796-preflight-agent-20261008-03'
need, digest = old.need, old.proof.gold.digest


def stride(size):
    need(type(size) is int and size == 16512 and size % 4 == 0,
         'Actual full two-phase/two-side snapshot ELF size')
    return size // 4


def checker():
    need(old.SNAP_SIZE == 4224, 'Preserved original checker stride error')
    return FunctionType(old.spike_gate.__code__, dict(old.spike_gate.__globals__,SNAP_SIZE=4128))


def collect():
    sources = json.loads((CAPTURE/'source_hashes.json').read_text())
    pins = dict(sources)
    for path, sha in sources.items():
        need(digest(Path(path)) == sha, 'Original03 source/helper pin changed: '+path)
    witness = json.loads(old.WITNESS.read_text())
    need(digest(old.WITNESS) == old.WITNESS_SHA, 'Frozen source proof')
    for path, sha in witness['pins'].items():
        need(digest(Path(path)) == sha, 'Source proof pin changed')
    pins.update(witness['pins'])
    latest = old.binding796(witness);pins.update(latest['pins'])
    need((CAPTURE/'qbs_fma_align795_data.h').read_text() == old.header(), 'Exact original packed input header')
    commands = json.loads((CAPTURE/'commands.json').read_text())
    manifest = json.loads(Path(latest['manifest']).read_text())
    for record in commands:
        need(record['cwd'] == str(old.ROOT) and record['status'] == 'PASS' and
             type(record['returncode']) is int and record['returncode'] == 0,
             'All actual compiler/host/Spike commands completed successfully')
        for path, sha in record['log_hashes'].items():
            need(digest(Path(path)) == sha, 'Original command log changed')
        executable = Path(record['command'][0]).resolve()
        if executable != (CAPTURE/'host-reference').resolve():
            need(str(executable) in manifest['input_pins'] and
                 digest(executable) == manifest['input_pins'][str(executable)], 'Tool identity differs from formal796')
            pins[str(executable)] = manifest['input_pins'][str(executable)]
    runs = [r for r in commands if Path(r['stdout']).name == 'spike.log']
    need(len(runs) == 1 and runs[0]['command'][-1] == str(CAPTURE/'reference.elf'),
         'Exactly one actual Spike execution, software reference only')
    old.host_gate((CAPTURE/'host-reference.log').read_text())
    metadata = {}
    for label in ('dut','reference'):
        path = CAPTURE/(label+'.elf')
        symbols, read = old.metadata(path)
        with path.open('rb') as stream:
            elf = ELFFile(stream)
            matches = [s for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name == 'qf_snap']
            need(len(matches) == 1 and stride(matches[0]['st_size']) == 4128, 'Actual compiled snapshot extent')
            need(all(0x80000000 <= s['p_vaddr'] and s['p_vaddr']+s['p_memsz'] <= 0x80200000
                     for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'), 'All ELF memory inside frozen2MiB SRAM')
        sites = ['qf_native_site'] if label == 'dut' else list(old.STAGES)
        words = [int.from_bytes(read(symbols[s],4),'little') for s in sites]
        need(words == ([0x00b5045b] if label == 'dut' else list(old.STAGE_WORDS)), 'Exact assembled instruction sites')
        metadata[label] = dict(elf=str(path),sha256=digest(path),symbols=symbols,
                               snapshot_stride=4128,snapshot_size=16512,sites=dict(zip(sites,words)))
    trace = CAPTURE/'spike.stderr.log'
    need('exception ' not in trace.read_text(), 'No actual Spike exception')
    commits = old.mature.shared.spike_trace.parse_spike_commits(trace)
    checks = checker()(commits,metadata['reference']['symbols'])
    for path in CAPTURE.iterdir():
        if path.is_file():pins[str(path)] = digest(path)
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_close_qbs_fma_align796_preflight.py'),
                 Path(old.mature.__file__),Path(old.mature.rv64c.__file__),Path(old.mature.shared.spike_trace.__file__)):
        pins[str(path)] = digest(path)
    for path, sha in pins.items():need(digest(Path(path)) == sha, 'Final closure pin drift')
    return dict(status='QBS_FMA_ALIGN796_HOST_SPIKE_PREFLIGHT_PASS_NOT_CUSTOM_NATIVE',
        capture=str(CAPTURE),pins=pins,baseline=latest,EL_seal=witness['EL_seal'],
        checks=checks,artifacts=metadata,
        offline_correction=dict(original_checker_stride=4224,actual_ELF_stride=4128,
            cause='Array object alignment does not round each unaligned struct element to128 bytes. Struct is16+4096+16=4128; actual4-element ELF symbol16512.',
            only_checker_global_replaced='SNAP_SIZE',all_original_sources_helpers_and_capture_bytes_unchanged=True),
        compiler_scalar_ISA='rv64gc_zfh with authored assembly .option arch,+v; C backend cannot inject RVV',
        full_packed_payload_bytes=2560,host_block_checks=8,host_destination_words=64,
        independent_gold='Packed Q4_K/Q8_K host qbs_ref decoder and exact rational RNE model agree; Spike explicit scalar FMUL/FMADD checks32 nan-boxed results.',
        software_reference_only=True,scalar_native_ISA_equality_claim=False,
        custom_native_execution_verified=False,native_qualified=False,coverage_admitted=False,
        padding_source_only_positions=56,padding_applied=False,
        mutable_missing796_host_one_witness_positions=latest['remaining_host_one_witness_positions'],
        measured_gain=None,coverage_percentage_claim=None,EDA_started=False,RTL_changed=False,
        instruction_budget_reference_retired=checks['retired'],
        future_native_obligations=['Full scalar/RVC/FP/memory comparison with custom-owner adapter, not raw fallback instruction equality',
            'Exactly two successful QBEXEC owners, four dot results each, full VRF/CSR/guards and source immutability',
            'Accepted FP operand/order, exponent_difference/addend_shamt and ten actual target coordinates',
            'Actual AXI/drain and relative latest formal raw bitmap/EL difference; no gain claimed until measurement'],
        previous_build_failures_preserved=['01 host header include path missing','02 reference link missing existing memset runtime'],
        recommendation='Only10 remaining host witness positions: preflight ready for review, not a material-gain or automatic-runtime authorization')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args();need(not args.output.exists(),'Fresh closure only')
    result = collect();args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(args.output),sha256=digest(args.output),checks=result['checks'],
                         remaining796=result['mutable_missing796_host_one_witness_positions'])))
