#!/usr/bin/env python3
"""One bounded real-DTLB MXR probe on pinned actual-SoC MMU sources; no RTL edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VERIFY = ROOT.parent / 'ara_dsa_signoff_integration'
RUNS = VERIFY / 'verification/out'
FROZEN = RUNS / 'e2e_physical_wide_soc_inputs_20261106_01'
FROZEN_PINS_SHA = '973525eaa572743307965c067267b2b2290b6e8ca7b7bffccc889f923feb3389'
FROZEN_RESULT_SHA = 'dad1e64aaa814f3fa4c5cf2d2bf3bb1ea105ca12aa1448ec3e8f0ae310942e29'
CORE = 'hardware/deps/cva6/core/'
COMMON = 'hardware/deps/common_cells/'
SOURCES = (
    COMMON+'src/cf_math_pkg.sv', CORE+'include/config_pkg.sv',
    CORE+'include/cv64a6_imafdcv_sv39_config_pkg.sv', CORE+'include/riscv_pkg.sv',
    CORE+'include/ariane_pkg.sv', CORE+'include/build_config_pkg.sv',
    COMMON+'src/lzc.sv', COMMON+'src/lfsr.sv',
    CORE+'pmp/src/pmp.sv', CORE+'pmp/src/pmp_entry.sv',
    CORE+'cva6_mmu/cva6_tlb.sv', CORE+'cva6_mmu/cva6_shared_tlb.sv',
    CORE+'cva6_mmu/cva6_ptw.sv', CORE+'cva6_mmu/cva6_mmu.sv',
)
EXTRA = (CORE+'cva6.sv', COMMON+'include/common_cells/assertions.svh',
         COMMON+'include/common_cells/registers.svh')
TYPE_NAMES = ('exception_t', 'icache_areq_t', 'icache_arsp_t', 'icache_dreq_t',
              'icache_drsp_t', 'dcache_req_i_t', 'dcache_req_o_t')
OBS_KEYS = 'case mxr hit latched_hit req valid is_store va pa pte exc cause tval refills flush'.split()
HEX_KEYS = {'va', 'pa', 'pte', 'tval'}
SCOPE = 'MMU_MXR_HIT_SCOPE pmp=0 rvh=0 sv=39 refill_only=1 cold_ptw=0 cases=5'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def expected_rows():
    rows = []
    for i, mxr in enumerate((0, 1, 1, 0, 1)):
        readable = i < 2
        va = 0x40000108 if readable else 0x40001108
        pa = 0x80010108 if readable else 0x80020108
        fault = i == 3
        rows.append(dict(case=i, mxr=mxr, hit=1, latched_hit=1, req=1, valid=1, is_store=0,
                         va=va, pa=pa, pte=((pa >> 12) << 10) | 0x41 | (2 if readable else 8),
                         exc=int(fault), cause=13 if fault else 0, tval=va if fault else 0,
                         refills=1 if readable else 2, flush=0))
    return rows


def audit(text, returncode):
    lines = text.splitlines()
    require(lines.count(SCOPE) == 1, 'Missing/duplicate exact scope')
    observed = []
    for line in lines:
        if not line.startswith('MMU_MXR_HIT_OBS '):
            continue
        pairs = [word.split('=') for word in line.split()[1:]]
        require(all(len(p) == 2 for p in pairs) and [p[0] for p in pairs] == OBS_KEYS,
                'Malformed/duplicate observation fields')
        row = {}
        for key, value in pairs:
            require(re.fullmatch('[0-9a-fA-F]+' if key in HEX_KEYS else '[0-9]+', value),
                    'Unknown/malformed observed value')
            row[key] = int(value, 16 if key in HEX_KEYS else 10)
        observed.append(row)
    wanted = expected_rows()
    require(len(observed) == 5, 'Incomplete/extra observations')
    failures = []
    for got, expected in zip(observed, wanted):
        for key in OBS_KEYS:
            if got[key] != expected[key]:
                failures.append(dict(case=expected['case'], field=key, got=got[key], expected=expected[key]))
    mismatches = re.findall(r'^MMU_MXR_MISMATCH case=(\d+) field=([A-Z_]+) got=([0-9a-f]{16}) expected=([0-9a-f]{16})$', text, re.M)
    mapped = {'hit':'LOOKUP_HIT', 'latched_hit':'LATCHED_HIT', 'req':'LATCHED_REQ',
              'pte':'LATCHED_PTE', 'is_store':'IS_STORE', 'valid':'VALID', 'pa':'PA',
              'exc':'EXCEPTION', 'cause':'CAUSE', 'tval':'TVAL'}
    require(all(f['field'] in mapped for f in failures), 'Stimulus/MXR/refill/flush identity failure')
    expected_mismatches = [(f['case'], mapped[f['field']], f['got'], f['expected']) for f in failures]
    actual_mismatches = [(int(i), key, int(a,16), int(b,16)) for i,key,a,b in mismatches]
    require(actual_mismatches == expected_mismatches, 'SV/host mismatch accounting differs')
    require(sum(line.startswith('MMU_MXR_MISMATCH') for line in lines) == len(mismatches),
            'Malformed extra mismatch')
    summary = re.findall(r'^MMU_MXR_HIT_COMPLETE cases=(\d+) checks=(\d+) errors=(\d+) refills=(\d+) ptw_requests=(\d+)$', text, re.M)
    require(summary == [('5','52',str(len(failures)),'2','0')], 'Incomplete summary/checks or unexpected PTW')
    require(not re.search(r'Error-\[|^\s*Error:|UVM_(?:ERROR|FATAL)|assertion[^\n]*fail|\$stop', text, re.I|re.M),
            'Unexpected simulator error')
    fatals = re.findall(r'^\s*Fatal:.*$', text, re.M)
    if failures:
        expected_line = next(i for i,line in enumerate((HERE/'mmu_mxr_hit_tb.sv').read_text().splitlines(),1)
                             if 'if (errors) $fatal(1, "MXR_HIT_CONTRACT_FAILED")' in line)
        require(len(fatals) == 1 and re.fullmatch(
            r'\s*Fatal: [^\n]*[/\\]mmu_mxr_hit_tb[.]sv, '+str(expected_line)+
            r': .*', fatals[0]) and
            '\nMXR_HIT_CONTRACT_FAILED\n' in text and
            re.search(r'^\s*Scope: mmu_mxr_hit_tb(?:[.][A-Za-z0-9_$]+)*\s*$', text, re.M),
            'Failure lacks one exact originating bench fatal')
    else:
        require(not fatals and returncode == 0 and '$finish called' in text, 'No clean terminal')
    reproduced = failures == [dict(case=3,field=k,got=0,expected=v)
                             for k,v in (('exc',1),('cause',13),('tval',0x40001108))]
    return dict(status='FAIL' if failures else 'PASS', observed=observed, failures=failures,
                checks=52, mxr_bypass_reproduced=reproduced, cold_ptw_covered=False,
                scope='Real MMU/DTLB hit permissions; refill input injection only; not SoC/AXI/CSR execution')


def extract_types(text):
    result = []
    for name in TYPE_NAMES:
        found = re.findall(r'(?:localparam|parameter)\s+type\s+'+name+
                           r'\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*,', text)
        require(len(found) == 1, 'Ambiguous actual CVA6 interface '+name)
        result.append('typedef '+found[0]+' '+name+';')
    return '\n'.join(result)+'\n'


def run(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS) and out != RUNS,
            'Fresh sole-verification output required')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='PREPARING', compile_count=0, simulation_count=0, performance_measured=False,
                  rtl_changed=False, cold_ptw_covered=False, full_soc=False)
    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = digest(path)
        require(expected is None or actual == expected, 'Input identity differs: '+str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'Pin conflict')
        pins[str(path)] = actual
    def verify():
        for path, sha in pins.items():
            require(digest(path) == sha, 'Pinned input drift: '+path)
    def freeze(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        pin(path)
    def command(argv, label, limit):
        directory = out/label; directory.mkdir()
        record = dict(argv=list(map(str,argv)), cwd=str(directory), timeout_seconds=limit)
        commands.append(record); save(out/'commands.json',commands)
        verify(); result['state'] = label.upper(); save(out/'status.json', result)
        start = time.monotonic()
        with (directory/'console.log').open('xb') as log:
            child = subprocess.Popen(record['argv'], cwd=directory, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            result['child_pid'] = child.pid; save(out/'status.json',result)
            try:
                record['returncode'] = child.wait(timeout=limit)
            except BaseException:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait(); raise
        result['child_pid'] = None
        record['elapsed_seconds'] = time.monotonic()-start
        save(out/'commands.json',commands); verify()
        return record['returncode'], (directory/'console.log').read_text()
    try:
        pin(FROZEN/'source-pins.json',FROZEN_PINS_SHA)
        pin(FROZEN/'result.json',FROZEN_RESULT_SHA)
        old_pins = json.loads((FROZEN/'source-pins.json').read_text())
        for relative in (*SOURCES,*EXTRA):
            source = FROZEN/'source'/relative
            pin(source,old_pins[str(source)])
            freeze(out/'inputs'/relative,source.read_bytes())
        for source in (HERE/'mmu_mxr_hit_tb.sv',Path(__file__),Path(sys.executable)):
            pin(source)
        bench = out/'inputs/verification/cva6/mmu_mxr_hit_tb.sv'
        freeze(bench,(HERE/bench.name).read_bytes())
        freeze(out/'generated/mmu_mxr_hit_types.svh',extract_types((out/'inputs'/CORE/'cva6.sv').read_text()).encode())
        vcs = Path(shutil.which('vcs') or '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
        pin(vcs)
        save(out/'source-pins.json',pins)
        result['source_pins_sha256'] = digest(out/'source-pins.json')
        result['dut_sha256'] = digest(out/'inputs'/CORE/'cva6_mmu/cva6_mmu.sv')
        build = out/'build'
        argv = [vcs,'-full64','-sverilog','-timescale=1ns/1ps','-assert','svaext',
                '+define+ARIANE_ACCELERATOR_PORT=1','-top','mmu_mxr_hit_tb',
                '-o',build/'simv','-Mdir='+str(build/'csrc'),
                '+incdir='+str(out/'inputs'/COMMON/'include'),
                '+incdir='+str(out/'inputs'/CORE/'include'),'+incdir='+str(out/'generated'),
                *(out/'inputs'/p for p in SOURCES),bench]
        result['compile_count'] = 1
        code, log = command(argv,'build',300)
        require(code == 0 and (build/'simv').is_file() and not re.search(r'Error-\[|Fatal:',log),
                'VCS compile failed')
        images = {str(p):digest(p) for p in [build/'simv',*(build/'simv.daidir').rglob('*.so')]}
        require(len(images)>1,'Missing compiled VCS design libraries')
        save(out/'image-pins.json',images)
        result['image_pins'] = images
        result['simulation_count'] = 1
        code, log = command([build/'simv','-no_save'],'sim',30)
        result['audit'] = audit(log,code)
        result['state'] = 'FAIL' if result['audit']['status']=='FAIL' else 'MMU_MXR_HIT_CONTRACT_PASS'
        result['finding'] = ('MXR_HIT_PERMISSION_BYPASS_REPRODUCED' if result['audit']['mxr_bypass_reproduced']
                             else 'NO_EXACT_BYPASS_REPRODUCTION')
        for path, sha in images.items():
            require(digest(path)==sha,'Image drift')
        verify(); result['post_pins_match'] = True
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc))
        try: verify(); result['post_pins_match'] = True
        except BaseException as drift: result['pin_error'] = repr(drift)
    finally:
        save(out/'commands.json',commands)
        result['artifacts'] = {str(p):digest(p) for p in out.rglob('*') if p.is_file() and
            (p.suffix in ('.json','.log','.sv','.svh') or p.name=='simv') and
            p.name not in ('result.json','status.json')}
        save(out/'status.json',result); save(out/'result.json',result)
    print(json.dumps({k:result.get(k) for k in ('state','finding','error','compile_count','simulation_count','post_pins_match')},indent=2))
    return 0 if result['state']=='MMU_MXR_HIT_CONTRACT_PASS' else 1


class AuditTests(unittest.TestCase):
    def fixture(self, bypass=False):
        rows = expected_rows()
        if bypass:
            rows[3].update(exc=0,cause=0,tval=0)
        lines = [SCOPE]
        for row in rows:
            if bypass and row['case']==3:
                for key,value in (('EXCEPTION',1),('CAUSE',13),('TVAL',0x40001108)):
                    lines.append(f'MMU_MXR_MISMATCH case=3 field={key} got={0:016x} expected={value:016x}')
            lines.append('MMU_MXR_HIT_OBS '+' '.join(k+'='+
                         (f'{row[k]:016x}' if k in HEX_KEYS else str(row[k])) for k in OBS_KEYS))
        lines.append('MMU_MXR_HIT_COMPLETE cases=5 checks=52 errors='+('3' if bypass else '0')+' refills=2 ptw_requests=0')
        if bypass:
            n = next(i for i,l in enumerate((HERE/'mmu_mxr_hit_tb.sv').read_text().splitlines(),1)
                     if 'if (errors) $fatal(1, "MXR_HIT_CONTRACT_FAILED")' in l)
            lines += [f'Fatal: /frozen/mmu_mxr_hit_tb.sv, {n}: unknown',
                      'MXR_HIT_CONTRACT_FAILED','  Scope: mmu_mxr_hit_tb']
        else:
            lines.append('$finish called')
        return '\n'.join(lines)+'\n'

    def test_success_is_not_a_reproduction(self):
        self.assertEqual(audit(self.fixture(),0)['status'],'PASS')
        self.assertFalse(audit(self.fixture(),0)['mxr_bypass_reproduced'])

    def test_exact_failure_remains_fail_even_exit_zero(self):
        value = audit(self.fixture(True),0)
        self.assertEqual(value['status'],'FAIL'); self.assertTrue(value['mxr_bypass_reproduced'])

    def test_missing_extra_unknown_and_changed_inputs_rejected(self):
        text = self.fixture()
        for broken in (text.replace('hit=1','hit=x',1),text.replace('mxr=0','mxr=1',1),
                       text.replace('checks=52','checks=51'),text.replace('cold_ptw=0','cold_ptw=1'),
                       text+'MMU_MXR_HIT_OBS case=5\n',text.replace('ptw_requests=0','ptw_requests=1')):
            with self.assertRaises(ValueError): audit(broken,0)

    def test_extra_wrong_origin_and_missing_fatal_rejected(self):
        text = self.fixture(True)
        for broken in (text+'Fatal: unrelated\n',text.replace('mmu_mxr_hit_tb.sv,','other.sv,'),
                       '\n'.join(l for l in text.splitlines() if not l.startswith('Fatal:')),
                       text.replace('Scope: mmu_mxr_hit_tb','Scope: other')):
            with self.assertRaises(ValueError): audit(broken,0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--self-test',action='store_true')
    args = parser.parse_args()
    if args.self_test:
        unittest.main(argv=[sys.argv[0]])
    else:
        require(args.output is not None,'--output required')
        def stop(sig,_frame): raise InterruptedError('Signal '+str(sig))
        for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,stop)
        sys.exit(run(args.output))
