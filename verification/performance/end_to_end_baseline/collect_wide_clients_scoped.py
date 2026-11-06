#!/usr/bin/env python3
"""Host-only source-location audit; neither sealed failed worker is relabelled."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import run_wide_clients as original

HERE = Path(__file__).resolve().parent
CHECKED = original.VERIFY/'verification/out/e2e_wide_clients_checked_20261106_01'
OUTPUT = original.VERIFY/'verification/out/e2e_wide_clients_scoped_20261106_01'
FIRST_SHA = 'e399f56fcafdf48863175fd0683f1c752f39c526cf63fa3e98c68acce7b37964'
CHECKED_SHA = 'e7d82aea3b55c5cfabdd0ffab90376cf3688576f185ae96ec1518bb9158efc2d'
CHECKED_PINS_SHA = '4de150a7313cfcb4a218cce20f60d5e992745173aa6a1e11be485df715f43296'
VIEW_SHA = '58203a859091699396dedb14a3deaacceb13747ed472459d009a8a5a72fd592e'
NORMAL_SHA = '31a91f1164b19ddf7ed1adbee0294de58852a9655174d124a183f4273797a153'
NEGATIVE_SHA = '7223d96bbf96c995357ba66b69d98b23f38fd54f687018e80cf00d2edd3b9a44'
RAW_ERROR = 'Fatal did not originate at the exact narrow-view guard'
INSTANCE = 'qbs_wide_clients_tb.copy256.dut.unnamed$$_2'
OWNED = ('collect_wide_clients_scoped.py', 'test_wide_clients_scoped.py')
require, digest, write = original.require, original.digest, original.write


def bind_property(source):
    pattern = (r'(?m)^  assert property \(@\(posedge clk_i\) disable iff \(!rst_ni\)\n'
               r'      wide_i\.data_valid \|-> \(wide_i\.data_strb >> 16\) == 0\)\n'
               r'    else \$fatal\(1, "QBS_READER_NARROW_VIEW_NONNARROW_PAYLOAD"\);$')
    blocks = list(re.finditer(pattern, source))
    require(len(blocks) == 1 and len(re.findall(r'\bassert\s+property\b', source)) == 1 and
            source.count(original.NEGATIVE_REASON) == 1, 'Missing/nonunique exact mask assertion')
    start = source.count('\n', 0, blocks[0].start())+1
    action = source.count('\n', 0, source.index('$fatal', blocks[0].start()))+1
    require((start, action) == (51, 53), 'Unexpected property/action source locations')
    return dict(property_line=start, fatal_action_line=action, block=blocks[0].group(),
                condition='wide_i.data_valid', consequent='(wide_i.data_strb >> 16) == 0',
                reason=original.NEGATIVE_REASON)


def scoped_negative(code, raw, dut):
    """Bind raw origin first; project only the fatal header's line for old gates."""
    binding = bind_property(Path(dut).read_text())
    try:
        original.check_negative(code, raw, dut)
    except ValueError as exc:
        require(str(exc) == RAW_ERROR, 'Not the sole authorized original-checker failure')
    else:
        raise ValueError('Original checker unexpectedly accepted raw log')
    require(len(re.findall(r'(?i)\bfatal\s*:', raw)) == 1, 'Expected exactly one GLOBAL fatal')
    headers = list(re.finditer(r'(?m)^Fatal: "(?P<file>[^"]+)", (?P<line>\d+): '
                               r'(?P<instance>[^\n]+): at time (?P<time>\d+) ps$', raw))
    require(len(headers) == 1, 'Missing/duplicate exact fatal header')
    header = headers[0]
    require(header.groupdict() == dict(file=str(dut), line='51', instance=INSTANCE, time='35000'),
            'Wrong source/property line/instance/time')
    diagnosis = f'"{dut}", 51: {INSTANCE}: started at 35000ps failed at 35000ps'
    require(raw.splitlines().count(diagnosis) == 1 and
            raw.splitlines().count("\tOffending '((wide_i.data_strb >> 16) == 0)'") == 1,
            'Missing/foreign assertion diagnosis or consequent')
    require(re.findall(r'\$finish called from file "([^"]+)", line (\d+)\.', raw) == [(str(dut), '51')],
            'Wrong/duplicate finish property origin')
    require(not re.search(r'(?i)\bPASS\b|WIDE_CLIENTS_\w*PASS', raw), 'PASS text in expected negative')
    projection = raw[:header.start('line')]+'53'+raw[header.end('line'):]
    # Every pre-existing return-code, global-fatal, path, reason, terminal,
    # finish-origin and unrelated-error gate runs unchanged on this projection.
    replay = original.check_negative(code, projection, dut)
    require(projection[:header.start('line')]+raw[header.start('line'):header.end('line')]+
            projection[header.start('line')+2:] == raw, 'Projection changed more than source-line metadata')
    return dict(raw_original_checker_failure=RAW_ERROR, raw_returncode=code, global_fatals=1,
                source=str(dut), instance=INSTANCE, binding=binding,
                scope='Only VCS concurrent-assertion fatal-header line attribution 51 -> action line 53',
                raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                projection_sha256=hashlib.sha256(projection.encode()).hexdigest(),
                raw_log_modified=False, original_negative_gates_replayed=True,
                projected_checker_result=replay), projection


def ownership():
    owned = {str(HERE/n) for n in OWNED}
    rows = []
    for directory in sorted((original.VERIFY/'verification/out').iterdir()):
        path = directory/'source-pins.json'
        if path.is_file():
            pins = json.loads(path.read_text())
            require(not owned.intersection(pins), 'Collector already sealed by another consumer: '+str(path))
            rows.append(dict(path=str(path), sha256=digest(path),
                             inherited_documentation=[k for k in pins if k.lower().endswith('.md')]))
    return rows


def pin_worker(c, root, expected, state, error):
    c.pin(root/'result.json', expected)
    result = json.loads((root/'result.json').read_text())
    require(result['state'] == state and result['error'] == error, 'Unexpected sealed-worker terminal')
    c.pin(root/'source-pins.json', result['source_pins_sha256'])
    for path, sha in json.loads((root/'source-pins.json').read_text()).items():
        c.pin(path, sha)
    for path, sha in result['artifacts'].items():
        c.pin(path, sha)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    require(args.collect, 'Explicit host-only collection required')
    inventories = ownership()
    OUTPUT.mkdir(exist_ok=False)
    c = original.Campaign(OUTPUT)
    result = dict(state='WIDE_CLIENTS_SCOPED_AUDIT_FAIL', actual_compiles=0, actual_simulations=0,
                  original_workers_relabelled=False, sealed_inputs_modified=False, rtl_changed=False,
                  soc_integrated=False, full_engines_executed=False, real_mmu_pmp_tested=False,
                  performance_measured=False, area_measured=False, production_deployment_approved=False)
    try:
        write(OUTPUT/'worker-pin-inventory.json', inventories)
        first = pin_worker(c, original.OUTPUT, FIRST_SHA, 'WIDE_CLIENTS_COMPONENT_FAIL',
                           "ValueError('First compile failure; preserved, do not rerun')")
        checked = pin_worker(c, CHECKED, CHECKED_SHA, 'WIDE_CLIENTS_CHECKED_COMPONENT_FAIL', repr(ValueError(RAW_ERROR)))
        require(checked['source_pins_sha256'] == CHECKED_PINS_SHA and
                checked['original_result_sha256'] == FIRST_SHA and
                checked['actual_compiles'] == 1 and checked['actual_simulations'] == 2,
                'Checked-worker source/execution identity')
        for relative, sha in original.INPUTS.items():
            c.pin(original.MAIN/relative, sha)
        dut = CHECKED/'source-snapshot/hardware/src/vlsu/qbs_reader_narrow_view.sv'
        c.pin(dut, VIEW_SHA)
        c.pin(CHECKED/'normal.log', NORMAL_SHA)
        c.pin(CHECKED/'negative-upper-mask.log', NEGATIVE_SHA)
        for name in OWNED:
            c.pin(HERE/name)
        c.pin(sys.executable)
        commands = json.loads((CHECKED/'commands.json').read_text())
        require([(r['label'], r['returncode']) for r in commands] ==
                [('unit-tests', 0), ('compile', 0), ('normal', 0), ('negative-upper-mask', 0)],
                'Unexpected actual execution inventory')
        image = CHECKED/'build/simv'
        require(commands[2]['argv'] == [str(image), '-no_save'] and
                commands[3]['argv'] == [str(image), '-no_save', '+NEGATIVE_UPPER_MASK'] and
                commands[1]['argv'][commands[1]['argv'].index('-o')+1] == str(image),
                'Executed image/negative invocation identity')
        write(OUTPUT/'source-pins-preaudit.json', c.pins)
        code, _ = c.run([sys.executable, '-B', HERE/'test_wide_clients_scoped.py'], 'unit-tests', 60)
        require(code == 0, 'Host-only scoped checker tests failed')
        measured = original.check_normal(commands[2]['returncode'], (CHECKED/'normal.log').read_text())
        negative, projection = scoped_negative(commands[3]['returncode'], (CHECKED/'negative-upper-mask.log').read_text(), dut)
        write(OUTPUT/'measured.json', measured)
        write(OUTPUT/'negative-source-location-audit.json', negative)
        with (OUTPUT/'negative-header-line-projection.log').open('x') as stream:
            stream.write(projection)
        c.verify()
        result.update(state='WIDE_CLIENTS_SCOPED_REAUDITED_WITH_EXACT_PROPERTY_GUARD', post_pins_match=True,
                      original_workers=[dict(path=str(original.OUTPUT), sha256=FIRST_SHA, state=first['state'], error=first['error']),
                                        dict(path=str(CHECKED), sha256=CHECKED_SHA, state=checked['state'], error=checked['error'])],
                      normal_status='PASS_UNCHANGED_ORIGINAL_CHECKER', negative_status='PASS_EXACT_PROPERTY_GUARD_SCOPED_AUDIT',
                      original_checker_failure=RAW_ERROR, negative=negative,
                      raw_normal_log=str(CHECKED/'normal.log'), raw_normal_sha256=NORMAL_SHA,
                      raw_negative_log=str(CHECKED/'negative-upper-mask.log'), raw_negative_sha256=NEGATIVE_SHA,
                      original_image=str(image), original_image_sha256=digest(image),
                      consumed_sources_sha256={name:digest(original.MAIN/name) for name in original.INPUTS},
                      cases=len(measured['cases']), fault_cases=len(measured['faults']), direct_copy_vectors=128,
                      measured=measured['summaries'], original_actual_compiles=1, original_actual_simulations=2,
                      scope='Source-location-only correction; both workers remain FAIL and raw logs stay unchanged',
                      limitations=['Synthetic clients on actual shared wrapper/reader/narrow view, not full engines',
                                   'Synthetic permission footprints and translation exception only, not real MMU/PMP',
                                   'No physical SoC width selection, SDK, performance, deployment or PPA acceptance'])
    except Exception as exc:
        result.update(error=repr(exc), post_pins_match=False)
    finally:
        write(OUTPUT/'source-pins.json', c.pins)
        write(OUTPUT/'path-identities.json', c.identities)
        write(OUTPUT/'commands.json', c.commands)
        result['source_pins_sha256'] = digest(OUTPUT/'source-pins.json')
        result['artifacts'] = {str(p):digest(p) for p in sorted(OUTPUT.iterdir())
                               if p.is_file() and p.name != 'result.json'}
        write(OUTPUT/'result.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return int(result['state'] != 'WIDE_CLIENTS_SCOPED_REAUDITED_WITH_EXACT_PROPERTY_GUARD')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
