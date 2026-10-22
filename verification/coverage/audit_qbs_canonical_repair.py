"""Strict 160-check QBS repair acceptance, independent of any old VCS image.

The caller supplies input.elf, run.vcs.log, console.log, commit_trace.csv,
vector_trace.csv and qbs-canonical-focused.vpd in one fresh run directory.
Use simulation_command() with a newly source-pinned FOR_VERIFY image. The
caller owns image/configuration provenance and simulator exit/timeout checks;
this module never builds, launches simulation or admits coverage.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import collect_gap71_canonical_qbs_positive779 as strict

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'verification/out/gap71-canonical779-qbs-positive-preflight-agent-20261008-03'
ORIGINAL_ELF = FIXTURE / 'input.elf'
ELF_SHA = 'a3c1d05bdf97312cdd8974f482e1d498a55fe150ec3bea097b2131f035693ec3'
REFERENCE_SHA = '0550849901af48c1e5e73adc40159514d899948a126d38a78ffd9e5e16404cc4'
PREFLIGHT_SHA = '2a73b8a7ee19b477288f6a6f1b021ca732b23e4917030a986ef31e329a50de39'
PROBE = ROOT / 'verification/coverage/gap71_canonical_qbs_positive779_probe.tcl'
CASE = 'gap71_canonical_qbs_repair'
TIMEOUT_SECONDS = 600
HELPER_PINS = {
    'verification/coverage/collect_gap71_canonical_qbs_positive779.py':
        'b28442199db367e7bcb83b0db847768408ab44623fb63e11b20b283d0071868e',
    'verification/coverage/run_gap71_canonical_qbs_positive779.py':
        '35bf42a74dfdd1c08187b27701e45b939333893d923cfbf6523c28457c2b2dce',
    'verification/coverage/preflight_gap71_canonical779.py':
        '2476f7e03866ba2ba08e5927e50a6761f03062b6d605e050fe5613cd46750d42',
    'verification/coverage/audit_gap71_custom.py':
        '1ac3d26202ff8b60a97e1040aaee79302f8072a65fb876ec3671d30de2be8c6e',
    'verification/coverage/custom_backend_lifetime.py':
        '8b4e2a0a87c1a72d7bafbca3b831108a14babcaa96b0b99ebb5756a8991179fb',
    'verification/ara_verify/vector_commit.py':
        'ed9e2cae2be4ab6d79eed5bf2499ad0f217bd116d3cba11b4454d42623c5a133',
    'verification/coverage/audit_gap115_axi_v2.py':
        '22f3198159b9a8488eed5034f2f9c4f707e19dbe43ce8175093505f3ba38f12f',
    'verification/coverage/gap71_canonical_qbs_positive779_probe.tcl':
        '3664c92213fe73d17a3547254434e614d9856cdcfb053b7c6445f3cc11747407',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def check_pins(pins):
    for name, expected in pins.items():
        require(digest(name) == expected, 'Input/checker hash changed: ' + str(name))


def fixture_contract(elf):
    # Bind software/oracle evidence, not preflight's historical RTL/image pins.
    pins = {str(ROOT / name): sha for name, sha in HELPER_PINS.items()}
    pins.update({str(FIXTURE / 'preflight.json'): PREFLIGHT_SHA,
                 str(FIXTURE / 'reference.elf'): REFERENCE_SHA,
                 str(elf): ELF_SHA})
    check_pins(pins)
    pre = json.loads((FIXTURE / 'preflight.json').read_text())
    require(pre['family'] == 'qbs' and pre['window'] == '0x1555400000'
            and pre['fault_address'] == '0x1555402080', 'Canonical fixture differs')
    require(pre['artifacts']['dut']['sha256'] == ELF_SHA
            and pre['artifacts']['dut']['metadata']['software_reference'] is False,
            'Native custom ELF required, not software fallback')
    require(pre['uart']['checks'] == 160 and pre['trace']['status'] == 'PASS'
            and pre['trace']['custom_instructions_executed'] == 0
            and pre['trace']['full_compared_words'] == 4688
            and pre['host_compared_words'] == 12288 and pre['host_numeric_words'] == 64,
            'Incomplete independent software oracle')
    pins[str(Path(__file__).resolve())] = digest(__file__)
    return pre['artifacts']['dut']['metadata'], pins


def simulation_command(image, directory):
    """Return argv only; caller copies ORIGINAL_ELF to directory/input.elf."""
    directory = Path(directory).resolve()
    return [str(Path(image).resolve()), '-l', 'run.vcs.log', '+NO_FSDB',
            '+ntb_random_seed=1', '+PRELOAD=' + str(directory / 'input.elf'),
            '+TESTCASE=' + CASE, '+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE=' + str(directory / 'commit_trace.csv'),
            '+VECTOR_TRACE=' + str(directory / 'vector_trace.csv'),
            '+QBS_PERF', '+ARA_DEBUG_EEW',
            '-cm', 'line+cond+fsm+tgl+branch',
            '-cm_dir', str(directory / 'code.vdb'), '-cm_name', CASE,
            '-ucli', '-do', str(PROBE)]


def log_gate(log):
    require(log.count('Core Test *** SUCCESS ***') == 1
            and 'Core Test *** FAILED ***' not in log
            and not re.search(r'(?m)^.*UVM_(?:ERROR|FATAL)(?!\s*:\s*0\s*$)', log)
            and not re.search(r'(?m)^\s*(?:Error|Fatal)(?:-|:)', log),
            'Simulator/self-check failure or assertion error')
    oracle = strict.runner.p.oracle(strict.runner.p.WINDOWS['positive'])
    uart = oracle['validate_log'](log, 'gap71_qbs_fault', 'custom-dut')
    require(uart['checks'] == 160, 'All 160 original checks required')
    return uart, oracle['runtime_perf'](log, 'gap71_qbs_fault')


def audit(directory):
    """Return strict evidence or raise; no old image/population qualification."""
    directory = Path(directory).resolve()
    elf = directory / 'input.elf'
    info, pins = fixture_contract(elf)
    names = ('input.elf', 'run.vcs.log', 'console.log', 'commit_trace.csv',
             'vector_trace.csv', 'qbs-canonical-focused.vpd')
    for name in names:
        path = directory / name
        require(path.is_file() and path.stat().st_size > 0,
                'Missing complete run artifact: ' + name)
    vpd = directory / names[-1]
    require(vpd.stat().st_size <= 64 * 1024 * 1024, 'Incomplete/oversized VPD')
    pins.update({str(directory / name): digest(directory / name) for name in names})
    uart, perf = log_gate((directory / 'run.vcs.log').read_text())
    console = (directory / 'console.log').read_text()
    # stderr assertions need not appear in VCS's -l file.
    log_gate(console)
    strict.markers(console)
    converter = strict.CONVERTER
    pins[str(converter)] = strict.CONVERTER_SHA
    check_pins(pins)
    output = directory / 'qbs-canonical-audit'
    output.mkdir(exist_ok=False)
    try:
        architecture = strict.native_architecture(
            directory / 'commit_trace.csv', directory / 'vector_trace.csv',
            info, elf.read_bytes(), output)
        require(architecture['owner']['full_scalar_compared_words'] == 4688,
                'Missing full PTE/data/guard/VRF/recovery readback')
        vcd = output / 'focused.vcd'
        with (output / 'conversion.log').open('x') as stream:
            subprocess.run([str(converter), '+splitpacked', str(vpd), str(vcd)],
                           stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
        require(vcd.is_file() and 0 < vcd.stat().st_size <= 512 * 1024 * 1024,
                'Missing/oversized converted cycle evidence')
        cycles = strict.cycle_wave(vcd, architecture['last_cycle'])
        check_pins(pins)
        result = dict(status='PASS', case=CASE, elf_sha256=ELF_SHA,
                      stdout=uart, architecture=architecture, perf=perf, cycles=cycles,
                      input_pins=pins,
                      output_pins={str(p): digest(p) for p in output.iterdir()},
                      coverage_admitted=False, old_vdb_reuse=False,
                      image_provenance_verified=False,
                      simulator_process_exit_verified=False,
                      independent_full_scalar_ISA_replay=False,
                      native_Spike_instruction_stream_comparison=False,
                      per_beat_protocol_certified=False,
                      scope='Canonical 160-check fault/retry and RVV recovery only; '
                            'caller must separately bind new image/source/config and process exit')
        (output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    except Exception as error:
        (output / 'rejection.json').write_text(json.dumps(
            dict(status='FAIL', reason=str(error), coverage_admitted=False), indent=2) + '\n')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), indent=2))
