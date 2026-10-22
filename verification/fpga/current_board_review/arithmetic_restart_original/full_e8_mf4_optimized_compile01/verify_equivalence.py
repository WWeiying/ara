"""Pin unchanged software semantics and the sole compiler optimization delta."""
from prepare import HERE, PARENT, SHAPES, read, save, sha, require, run

OLD = PARENT / 'full_e8_mf4_prepare01'
OLD_READY = '564f56d49179ae95a903e12fca86f3afe80e974a7f29327f5a7fe531c56d4ea5'

def main():
    require(sha(OLD/'READY.json') == OLD_READY, 'Sealed Os READY changed')
    oldready = read(OLD/'READY.json')
    require(oldready['firmware_through_htif'] == 7219909 and not oldready['DUT_started'], 'Os baseline identity')
    evidence = read(OLD/'evidence_pins.json')
    for path, digest in evidence.items():
        require(sha(path) == digest, 'Sealed Os evidence drift '+path)
    name = SHAPES[0]['id']
    root = HERE/name
    files = ['model.py', 'host_model.c', 'reference.py', 'bss_guard.py',
        'runtime/startup.S', 'runtime/runtime.c', 'runtime/replay.ld']
    files += [name+'/'+x for x in ('case.c', 'main.c', 'runtime.diff', 'model.json',
        'original/scenario.S', 'original/operations.h', 'original/reconstructed_oracle.c', 'host/host_rows.h')]
    identical = {}
    for relative in files:
        require(sha(HERE/relative) == sha(OLD/relative), 'Source/model/observer drift '+relative)
        identical[relative] = sha(HERE/relative)
    require((HERE/'prepare.py').read_text() == (OLD/'prepare.py').read_text().replace("flags=['-Os'", "flags=['-O2'"),
        'Preparation delta must be exactly Os to O2')
    expected_checker = (OLD/'reference_check.py').read_text().replace(
        "    helpers=spec['helpers'];lookup=", "    failure_entries={address for name,address in symbols.items() if name=='failure' or name.startswith('failure.')}\n"
        "    require(failure_entries,'Actual compiler failure entry required')\n    helpers=spec['helpers'];lookup=").replace(
        "if pc==symbols['failure']:", "if pc in failure_entries:")
    require((HERE/'reference_check.py').read_text() == expected_checker, 'Only mature compiler failure-entry adaptation allowed')
    oldproof = read(OLD/name/'sourceproof.json')
    proof = read(root/'sourceproof.json')
    require(proof['case'] == oldproof['case'], 'Full geometry drift')
    for backend in ('soc', 'spike'):
        oldcmd = read(OLD/name/backend/'compile.log.command.json')['command']
        newcmd = read(root/backend/'compile.log.command.json')['command']
        expected = [x.replace(str(OLD), str(HERE)) if x != '-Os' else '-O2' for x in oldcmd]
        require(newcmd == expected, 'Unexpected compiler delta '+backend)
        helpers = proof['backends'][backend]['helpers']
        require(len(helpers) == 26, 'All original routines required')
        for function, window in helpers.items():
            require([x['insn'] for x in window] == [x['insn'] for x in oldproof['backends'][backend]['helpers'][function]],
                'Helper encoding drift '+function)
        allowed = {x['pc'] for window in helpers.values() for x in window}
        for pc, insn in proof['backends'][backend]['code'].items():
            vector = insn & 127 == 0x57 or insn & 127 in (7,39) and (insn>>12)&7 in (0,5,6,7)
            require(not vector or int(pc) in allowed, 'Extra compiled vector instruction')
    host = root/'host'
    run(['/usr/bin/cc', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
        '-fno-sanitize-recover=undefined', '-fsanitize-undefined-trap-on-error', '-DSEW=8',
        '-I'+str(root/'original'), '-I'+str(host), root/'case.c', HERE/'host_model.c', '-o',
        host/'model_ubsan_trap'], host/'ubsan_trap_compile.log')
    run([host/'model_ubsan_trap'], host/'ubsan_trap_positive.log')
    require('HOST_END calls=4095 injected=0 result=0' in (host/'ubsan_trap_positive.log').read_text(), 'Full UBSan completion')
    pins = read(HERE/'input_pins.json')
    pins.update(evidence)
    pins[str(OLD/'READY.json')] = OLD_READY
    mature = PARENT/'full_e64_m1_optimized_compile01'
    for f in (mature/'STATIC_BASIS.md', mature/'prepare.py', HERE/'STATIC_BASIS.md', HERE/'verify_equivalence.py'):
        pins[str(f)] = sha(f)
    save(HERE/'equivalence.json', dict(status='SOLE_O2_DELTA_FULL_SOURCE_HELPERS_HOST_UBSAN_PASS_NOT_DUT',
        old_ready_sha256=OLD_READY, old_firmware=7219909, identical_files=identical,
        same_original_calls=4095, same_results=131040, same_guards=8190, same_vstart_checks=4095,
        same_model_full=True, helper_routines_per_backend=26, helper_target_bytes_unchanged=True,
        host_positive=1, host_negative=8, additional_full_ubsan_positive=1, pins=pins))
    print('SOLE_O2_DELTA_FULL_SOURCE_HELPERS_HOST_UBSAN_PASS_NOT_DUT', flush=True)

if __name__ == '__main__': main()
