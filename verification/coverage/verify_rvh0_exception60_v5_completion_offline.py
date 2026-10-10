"""Read-only full inspect replay and explicit post-wrapper stdout closure."""
import argparse
import ast
import hashlib
import inspect
import json
from pathlib import Path
from types import FunctionType

import rvh0_exception60_native772_v5 as native

OUT = native.life.OUT / 'rvh0-exception60-native772-v5-agent-prepared-20261007-01'
CONFIG_SHA = '8321726a1f6a2d279b64e8fdfcdeb526067bcb005db45a2fca51a793b667d164'
RESULT_SHA = '9648c27d3f0c753be0d8f4a142a645f2e6c627b0782565371d765e0eb3b43d36'
need = native.need


def stdout_closure(data, snapshot_sha, terminal, result_path, result_sha):
    lines = data.splitlines(keepends=True)
    need(len(lines) == 2 and all(line.endswith(b'\n') for line in lines), 'Exactly prefix plus one complete receipt line')
    prefix, suffix = lines
    need(hashlib.sha256(prefix).hexdigest() == snapshot_sha, 'Exact old sealed stdout prefix')
    need(json.loads(prefix) == {'actual_dve': terminal['actual_dve']}, 'Prefix terminal/live identity')
    receipt = {'result': str(result_path), 'seal': result_sha}
    need(suffix == (json.dumps(receipt) + '\n').encode(), 'Exact wrapper receipt bytes; no arbitrary tail')
    return dict(original_snapshot_sha256=snapshot_sha, original_snapshot_bytes=len(prefix),
                final_file_sha256=hashlib.sha256(data).hexdigest(), final_file_bytes=len(data),
                suffix_bytes=len(suffix), suffix_sha256=hashlib.sha256(suffix).hexdigest(),
                suffix_receipt=receipt, original_whole_file_pin_matches_current=False,
                original_prefix_bytes_exact=True)


def collect():
    result_path = OUT / 'capture-result.json'
    result = native.life.read_bound(result_path, RESULT_SHA)
    config = native.verify_config(OUT, CONFIG_SHA)
    terminal = json.loads((OUT / 'terminal.json').read_bytes())
    service = OUT / 'service.log'
    closure = stdout_closure(service.read_bytes(), result['pins'][str(service)],
                             terminal, result_path, RESULT_SHA)
    differences = {path for path, sha in result['pins'].items() if native.life.digest(path) != sha}
    need(differences == {str(service)}, 'No other sealed pin may change')
    all_files = {str(p) for p in OUT.rglob('*') if p.is_file()}
    expected_files = {path for path in result['pins'] if Path(path).is_relative_to(OUT)} | {str(result_path)}
    need(all_files == expected_files, 'No new/deleted files in original capture directory')

    # Execute every original inspect gate without writing or removing its old receipt.
    writes = []

    class ReadOnlyLife:
        def __getattr__(self, name):
            return getattr(native.life, name)

        def save(self, path, fresh):
            need(path == result_path, 'Replay may only propose the original receipt')
            need(fresh['pins'][str(service)] == closure['final_file_sha256'], 'Final stdout observed')
            preserved = dict(fresh, pins=dict(fresh['pins']))
            preserved['pins'][str(service)] = result['pins'][str(service)]
            need(preserved == result, 'All original receipt fields/pins equal except proven stdout append')
            writes.append(fresh)

    def replay_need(condition, message):
        if message == 'Fresh result only':
            need(not condition and result_path.is_file() and native.life.digest(result_path) == RESULT_SHA,
                 'Read-only existing receipt identity')
        else:
            need(condition, message)

    namespace = dict(native.inspect.__globals__, life=ReadOnlyLife(), need=replay_need,
                     print=lambda *args, **kwargs: None)
    FunctionType(native.inspect.__code__, namespace)(OUT, CONFIG_SHA)
    need(len(writes) == 1, 'Original inspect completed exactly once without writes')

    inspect_source = inspect.getsource(native.inspect)
    host_source = inspect.getsource(native.host.run)
    function = ast.parse(inspect_source).body[0]
    need(isinstance(function.body[-2], ast.Expr) and function.body[-2].value.func.attr == 'save'
         and isinstance(function.body[-1], ast.Expr) and function.body[-1].value.func.id == 'print',
         'Sealed inspect saves result then prints receipt')
    need(host_source.index("life.save(out / 'terminal.json'") < host_source.index('try: verify(out, seal)'),
         'Host waits/records terminal before calling qualification')
    runner = native.HERE / 'run_rvh0_exception60_native772_v5.py'
    adapter = native.HERE / 'run_rvh0_exception60_native772_v2.py'
    need('qualification=qualification' in runner.read_text()
         and 'verify=qualification.inspect' in adapter.read_text(), 'Private runner binds frozen qualification inspect')

    completed_pins = dict(result['pins'])
    completed_pins[str(service)] = closure['final_file_sha256']
    completed_pins[str(result_path)] = RESULT_SHA
    dependencies = [Path(__file__).resolve(), Path(__file__).with_name('test_verify_rvh0_exception60_v5_completion_offline.py'),
                    runner, adapter]
    completed_pins.update({str(p): native.life.digest(p) for p in dependencies})
    native.life.check(completed_pins)
    stages = [dict(stage=s, objects=2854, targets_excluded=60 if s in ('selected', 'reloaded') else 0,
                   protected_excluded=0, protected_arrays=38) for s in native.STAGES]
    return dict(status='RVH0_EXCEPTION60_POST_WRAPPER_OFFLINE_CLOSURE_PASS_NOT_POPULATION_APPLIED',
                original_capture_result=str(result_path), original_result_sha256=RESULT_SHA,
                original_config_sha256=CONFIG_SHA, original_receipt_preserved=True,
                original_sealed_pin_map_anchor=dict(path=str(result_path), sha256=RESULT_SHA, member='pins', count=217),
                original_whole_file_matches=216, original_whole_file_changed_pins=[str(service)],
                mutable_launcher_logs=[str(OUT / n) for n in ('service.log', 'launcher.log', 'xvfb.log')],
                mutable_log_change_allowed_only_by_exact_proven_stdout_suffix=True,
                immutable_native_source_config_pins_match=True, no_new_capture_files=True,
                stdout_closure=closure, terminal=terminal, stages=stages,
                actual_inventory_files_checked=25, objects_per_stage=2854, targets=60, protected=2794,
                typed_EL_semantic_records=79, scalar_direction_records=38, whole_vectors=41,
                global_EL_protects_children=True, empty_before_reset_final_cleanup=True,
                original_inspect_all_checks_replayed=True, original_receipt_reconstruction_equal_with_snapshot=True,
                wrapper_source_proof=dict(inspect_save_then_print=True, host_terminal_then_inspect=True,
                                          inspect_source_path=native.predecessor.__file__, runner=str(runner), adapter=str(adapter)),
                no_EDA_launched=True, population_applied=False, official_percentage=None,
                completion_pins=completed_pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    receipt = collect()
    if args.verify:
        need(json.loads(args.verify.read_bytes()) == receipt, 'Exact completion closure replay')
        print('RVH0_EXCEPTION60_OFFLINE_COMPLETION_REPLAY_PASS')
    else:
        need(args.output and args.output.absolute().parent == native.life.OUT and not args.output.exists(),
             'Fresh independent offline receipt outside frozen capture directory')
        native.life.save(args.output, receipt)
        print(json.dumps(dict(receipt=str(args.output), seal=native.life.digest(args.output))))
