"""Offline e0784 semantics and current VDB identity; never old-image admission.

Input: RUN/plan.json (command, work, pins, elf_sha256, index=784),
RUN/simulation-exit.json (executed, returncode, timed_out, cancelled, command,
cwd, elapsed_s), RUN/console.log, and WORK native traces/log/code.vdb.
Output must be fresh. No simulation, old prepared context, or coverage gain.
"""
import argparse
import json
import math
from pathlib import Path
import shlex
import sys

# Reuse the repository's vendored parser without a pip install or /tmp dependency.
VENDORED_ELF = (Path(__file__).resolve().parents[2] /
                'hardware/fpga/ara_dsa_vcu118/software/vendor/pyelftools-0.32-py3-none-any.whl')
sys.path.insert(0, str(VENDORED_ELF))
from elftools.elf.elffile import ELFFile

import collect_valu_restart783 as semantic
import run_vcs_dve_batch as batch

gold, life, require = semantic.gold, semantic.life, semantic.require
ROOT = gold.ROOT
PREFLIGHT_SHA = '30490ac0a6805d6609282162a675bce9557a4a00dfdd997efe59c0f88c6723d9'
ELF_SHA = 'c64a89540ff1c37ea3e1a2adefcb86694547f12032d8acc30cb1fa90d6c8520d'
CASE = 'valu_restart783_e8m8_12'
FREEZE = ROOT / 'verification/out/full-regression-20261015-01/freeze.json'


def read(path):
    return json.loads(path.read_bytes())


def option(command, name):
    if name.startswith('+'):
        values = [arg[len(name) + 1:] for arg in command if arg.startswith(name + '=')]
    else:
        values = [command[i + 1] for i, arg in enumerate(command[:-1]) if arg == name]
        require(command[-1] != name, 'Missing option value: ' + name)
    require(len(values) == 1, 'One command option required: ' + name)
    return values[0]


def terminal(actual, command, work):
    require(actual.get('executed') is True and type(actual.get('returncode')) is int
            and actual['returncode'] == 0 and actual.get('timed_out') is False
            and actual.get('cancelled') is False, 'Normal typed simulator terminal required')
    elapsed = actual.get('elapsed_s')
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed > 0,
            'Finite actual numeric wait required')
    require(actual.get('command') == command and actual.get('cwd') == str(work),
            'Actual command/cwd differs from plan')


def reference_binding(elf, expected):
    prepath = gold.OUT / 'preflight.json'
    pre = life.read_bound(prepath, PREFLIGHT_SHA)
    require(pre['status'] == 'VALU_RESTART783_SPIKE_FULL_BEFORE_AFTER_VRF_CSR_GUARDS_PASS_NOT_DUT',
            'Full reference preflight required')
    reference_elf, trace = gold.OUT / 'input.elf', gold.OUT / 'spike.trace'
    require(expected == ELF_SHA and pre['pins'][str(reference_elf)] == ELF_SHA
            and life.digest(elf) == life.digest(reference_elf) == ELF_SHA,
            'Replay/reference e0784 ELF mismatch')
    pins = {str(prepath): PREFLIGHT_SHA, str(reference_elf): ELF_SHA,
            str(elf): ELF_SHA, str(trace): pre['pins'][str(trace)]}
    life.check(pins)
    with elf.open('rb') as stream:
        table = ELFFile(stream).get_section_by_name('.symtab')
        require(table is not None, 'Replay ELF symbol table required')
        symbols = {s.name: s['st_value'] for s in table.iter_symbols() if s.name in gold.NAMES}
    require(symbols == pre['symbols'] and symbols['tohost'] == 0x80001000,
            'Preflight symbols must bind actual replay ELF')
    return pre, pins


def bind_run(run):
    planpath, actualpath = run / 'plan.json', run / 'simulation-exit.json'
    plan, actual = read(planpath), read(actualpath)
    require(type(plan.get('index')) is int and plan['index'] == 784, 'Only e0784 supported')
    command = plan['command']
    require(isinstance(command, list) and command and all(isinstance(a, str) for a in command),
            'Actual argv array required')
    work = Path(plan['work'])
    require(work.is_absolute() and work.resolve() == work and work.is_relative_to(run),
            'Native work must belong to replay directory')
    terminal(actual, command, work)
    require(isinstance(plan['pins'], dict) and plan['pins'], 'Pinned replay inputs required')
    require(all(Path(p).is_absolute() for p in plan['pins']), 'Absolute pin paths required')
    life.check(plan['pins'])
    elf = Path(option(command, '+PRELOAD'))
    require(elf.is_absolute() and plan['pins'].get(str(elf)) == ELF_SHA,
            'Plan must pin exact e0784 input ELF')
    pre, pins = reference_binding(elf, plan['elf_sha256'])
    freeze = read(FREEZE)
    require(command[0] == freeze['simv'] and command[0] in freeze['image'],
            'Replay must use current campaign image')
    life.check(freeze['image'])
    require(option(command, '+TESTCASE') == CASE and option(command, '-cm_name') == CASE
            and option(command, '+COMMIT_TOHOST') == '80001000'
            and option(command, '-cm') == 'line+cond+fsm+tgl+branch'
            and option(command, '+ntb_random_seed') == '1'
            and command.count('+NO_FSDB') == 1, 'Exact replay stimulus/coverage contract')
    for name, filename in (('+COMMIT_TRACE', 'commit_trace.csv'),
                           ('+VECTOR_TRACE', 'vector_trace.csv'),
                           ('-cm_dir', 'code.vdb'), ('-l', 'run.vcs.log')):
        value = option(command, name)
        require(Path(value) == work / filename or (name == '-l' and value == filename),
                'Native output path differs: ' + name)
    pins = life.merge_pins(life.merge_pins(pins, plan['pins']), freeze['image'])
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in (planpath, actualpath, FREEZE)})
    return plan, actual, pre, work, pins


def vdb_identity(work, command):
    vdb = work / 'code.vdb'
    files = batch.valid_vdb(vdb, CASE, command[0])
    native = vdb / 'snps/coverage/db/testdata' / CASE
    info = semantic.toggle.xml(native / 'siminfo.xml').find('srctest')
    require(info is not None and int(info.get('starttime', '0')) > 0
            and shlex.split(info.get('cmdline', '')) == command
            and info.get('workdir') == str(work), 'Complete actual VDB argv/workdir identity')
    return dict(status='PASS', vdb=str(vdb), test=CASE,
                starttime=int(info.get('starttime')), finishtime=int(info.get('finishtime')),
                files=files)


def check_semantics(work, console_path, pre, output):
    decode, shared, mature, generic = semantic.decode, semantic.shared, semantic.mature, semantic.generic
    prefix, rows, end = decode.prefix((work / 'commit_trace.csv').read_bytes())
    require(end['ignored_postterminal_bytes'] == 0, 'Post-terminal commit events')
    vectors = decode.table((work / 'vector_trace.csv').read_bytes(), decode.VECTOR_FIELDS)
    require(all(int(v['cycle']) <= end['cycle'] for v in vectors), 'Post-terminal vector activity')
    prefix_path = output / 'commit-prefix.csv'
    prefix_path.write_bytes(prefix)
    trace = gold.OUT / 'spike.trace'
    reference = shared.spike_trace.parse_spike_commits(trace)
    reference = reference[next(i for i, c in enumerate(reference) if c.pc == 0x80000000):]
    reference = reference[:next(i for i, c in enumerate(reference)
                                if (0x80001000, 1) in c.memory_accesses) + 1]
    memory, reads = mature.scalar_check(rows, reference, pre['symbols'])
    semantic.memory_oracle(memory, reads, pre['symbols'])
    control, req, resp = semantic.lifecycle(rows, vectors)
    console, vcslog = console_path.read_text(), (work / 'run.vcs.log').read_text()
    protocol = mature.protocol(console, req, resp, end['cycle'])
    generic.logs(console, vcslog, control)
    require('Coverage status: End of All Coverages' in console, 'Native coverage end required')
    scalar = shared.spike_trace.compare_commit_prefix(
        trace, prefix_path, 0x80000000, terminal_tohost_address=0x80001000,
        rvfi_store_data_layout='unshifted')
    shared.scalar_exact(scalar, pre['counts'])
    vector = shared.compare_vector_commits(trace, prefix_path, work / 'vector_trace.csv', 0x80000000)
    semantic.vector_gate(vector)
    vc = generic.vc
    lanes, vlen, activities = vc._parse_vector_trace(work / 'vector_trace.csv')
    starts, retires, traps = vc._parse_architecture_mapping(prefix_path)
    arch = vc._map_architecture_retires(starts, retires, traps, allow_incomplete_tail=False)
    stream = vc._spike_from_entry(trace, 0x80000000)
    mapping = vc._map_spike_commits(arch, stream, allow_incomplete_tail=False)
    receipts = []
    for seq, index in sorted(mapping.items()):
        if stream[index].instruction != gold.OPCODE:
            continue
        require(seq in activities, 'Missing native target')
        receipt = semantic.target_bytes(vc._architectural_bytes(activities[seq].writes, lanes, vlen),
                                        len(receipts))
        receipts.append(dict(receipt, arch_seq=seq))
    require(len(receipts) == 12, 'Twelve independent native target oracles required')
    return dict(scalar=scalar, vector=vector, lifecycle=control, protocol=protocol,
                per_instruction_oracles=receipts, terminal=end,
                full_scalar_retirements=len(reference), software_checks=13144,
                full_VRF_snapshot_bytes=98304, guard_bytes=3072, source_guard_bytes=3200,
                CSR_words=60, all_scalar_RVC_memory_checked=True,
                scalar_trap_rows_required=0, unknown_defined_bytes_skipped=0)


def audit(run, output):
    run, output = run.resolve(strict=True), output.absolute()
    require(output.resolve() == output and output != run and not run.is_relative_to(output),
            'Independent audit destination required')
    output.mkdir(parents=True, exist_ok=False)
    pins = {}
    try:
        plan, actual, pre, work, pins = bind_run(run)
        console = run / 'console.log'
        if not console.is_file():
            console = work / 'console.log'
        inputs = [console, work / 'run.vcs.log', work / 'commit_trace.csv', work / 'vector_trace.csv']
        inputs += [p for p in (work / 'code.vdb').rglob('*') if p.is_file()]
        # Freeze native inputs before parsing; recheck after the entire audit.
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in inputs})
        modules = {Path(__file__).resolve(), VENDORED_ELF}
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_relative_to(ROOT / 'verification') and Path(path).is_file():
                modules.add(Path(path).resolve())
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in modules})
        identity = vdb_identity(work, plan['command'])
        result = check_semantics(work, console, pre, output)
        life.check(pins)
        result.update(status='PASS', kind='VALU_REPLAY_FULL_ARCHITECTURE_CURRENT_IMAGE',
                      run=str(run), actual=actual, current_vdb=identity, pins=pins,
                      coverage_admitted=False, official_percentage=False,
                      scope='Current replay semantic audit and VDB identity only; no old target coverage gain')
        life.save(output / 'qualification.json', result)
        print(json.dumps(dict(status=result['status'], output=str(output / 'qualification.json'))))
        return result
    except Exception as error:
        life.save(output / 'rejection.json', dict(status='FAIL', reason=type(error).__name__ + ': ' + str(error),
                                                run=str(run), pins=pins, coverage_admitted=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.run, args.output)


if __name__ == '__main__':
    main()
