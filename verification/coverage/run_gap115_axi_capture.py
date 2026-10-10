"""One bounded same-ELF AXI-only UCLI capture; not qualification/admission."""
import argparse
import json
from pathlib import Path
import subprocess
import run_gap95_simulation as life

OLD = life.OUT/'gap115-active-div-reset-old-image-742-20261007-01'
OLD_SHA = '5ff5ef8d1a36795252554c39817735298a84122fb9b4a8c2a5d691e21d588dd1'
OUT = life.OUT/'gap115-axi-only-old-image-20261007-01'
TCL = Path(__file__).with_name('gap115_axi_only.tcl').resolve()
HOME = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')
CONVERTER = HOME/'linux64/bin/vpd2vcd.exe'
CONVERTER_SHA = '195fae31e4cbacabcbbd97bfd61c98a333f68ff2fd013002ab322e5108f97002'
DOC = HOME/'doc/UserGuide/pdf/ucli_ug.pdf'
DOC_SHA = '12e52cf0e7a3ceb601a1e0dc24d0516b03621163c8ec6066bbbc12e163fd6a34'


def command(old):
    cmd = list(old)
    expected = {'+COMMIT_TRACE=': OUT/'commit_trace.csv', '+VECTOR_TRACE=': OUT/'vector_trace.csv'}
    for prefix, path in expected.items():
        if sum(x.startswith(prefix) for x in cmd) != 1: raise ValueError('Missing/duplicate trace argument')
        cmd = [prefix+str(path) if x.startswith(prefix) else x for x in cmd]
    if cmd.count('-cm_dir') != 1: raise ValueError('Coverage path argument differs')
    cmd[cmd.index('-cm_dir')+1] = str(OUT/'code.vdb')
    if '-ucli' in cmd or '-do' in cmd: raise ValueError('Original command already has debugger script')
    return cmd+['-ucli', '-do', str(TCL)]


def prepare():
    original = life.read_bound(OLD/'manifest.json', OLD_SHA)
    pins = life.merge_pins(original['pins'], {str(OLD/'manifest.json'): OLD_SHA})
    for path, sha in [(DOC, DOC_SHA), (CONVERTER, CONVERTER_SHA),
                      (TCL, life.digest(TCL)), (Path(__file__).resolve(), life.digest(Path(__file__).resolve())),
                      (Path(__file__).with_name('test_run_gap115_axi_capture.py'),
                       life.digest(Path(__file__).with_name('test_run_gap115_axi_capture.py'))),
                      (Path(life.__file__).resolve(), life.digest(Path(life.__file__).resolve()))]:
        pins = life.merge_pins(pins, {str(path): sha})
    if original['timeout_s'] != 600 or original['case'] != 'vgap115_active_div_reset':
        raise ValueError('Original case/budget differs')
    life.check(pins)
    record = dict(case=original['case'], pins=pins, command=command(original['command']), timeout_s=600,
                  old_manifest_seal=OLD_SHA, unchanged_ELF=True, coverage_admitted=False,
                  uvm_check_report_pass=False, capture_only=True, wave_byte_limit=64*1024*1024,
                  objects=['clk_i', 'rst_ni', 'axi_req_o', 'axi_resp_i'], no_RTL_change=True)
    target = OUT.with_name(OUT.name+'.prepared.json')
    if OUT.exists(): raise ValueError('Output already exists')
    life.save(target, record)
    print(json.dumps(dict(prepared=str(target), seal=life.digest(target))))


def run(seal):
    target = OUT.with_name(OUT.name+'.prepared.json')
    record = life.read_bound(target, seal)
    record['pins'] = life.merge_pins(record['pins'], {str(target): seal})
    if OUT.exists(): raise ValueError('No retry/overwrite')
    life.run(OUT, record)
    wave = OUT/'axi-only.vpd'
    text = (OUT/'console.log').read_text()
    if text.count('GAP115_AXI_FOUR_OBJECTS_READY') != 1 or 'GAP115_AXI_CAPTURE_ERROR' in text:
        raise ValueError('Actual UCLI object setup rejected')
    if not wave.is_file() or not 0 < wave.stat().st_size <= record['wave_byte_limit']:
        raise ValueError('Missing/oversized focused VPD')
    with (OUT/'conversion.log').open('x') as log:
        subprocess.run([str(CONVERTER), '+splitpacked', str(wave), str(OUT/'axi-only.vcd')],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    life.check(record['pins'])
    life.save(OUT/'capture-status.json', dict(status='FOCUSED_VPD_VCD_CAPTURED_NOT_AXI_QUALIFIED',
        wave_pins={str(p): life.digest(p) for p in (wave, OUT/'axi-only.vcd', OUT/'conversion.log')},
        coverage_admitted=False, uvm_check_report_pass=False, original_fail_preserved=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--run-seal')
    args = parser.parse_args()
    if bool(args.prepare) == bool(args.run_seal): parser.error('Prepare or one sealed run')
    if args.prepare: prepare()
    else:
        try: run(args.run_seal)
        except Exception as exc:
            if OUT.exists() and not (OUT/'capture-failure.json').exists():
                life.save(OUT/'capture-failure.json', dict(reason=str(exc), no_retry=True, coverage_admitted=False))
            raise
