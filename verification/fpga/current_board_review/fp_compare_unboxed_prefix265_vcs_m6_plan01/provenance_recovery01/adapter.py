"""Owned successor utilities; never change sealed cases or old run metadata."""
import hashlib
import json
import os
from pathlib import Path

NAME = 'fp_compare_unboxed_e16_mf4_prefix265'
HISTORICAL_NAME = 'rvv_fp_compare_unboxed_unmasked_e16_mf4'


def runtime_case(case):
    if case['id'] != NAME or case['original_name'] != HISTORICAL_NAME:
        raise ValueError('Unexpected original/runtime identity')
    return dict(case, original_name=case['id'])


def persist_unvalidated_outcome(result):
    """Only for future executions, immediately after the parent runner returns."""
    root = Path(result.artifact_dir)
    record = dict(schema='UNVALIDATED_CHILD_OUTCOME_V1',
                  architectural_acceptance=False, name=result.name,
                  status=result.status, returncode=result.returncode,
                  elapsed_s=result.elapsed_s, reason=result.reason,
                  artifact_dir=str(root), command_path=str(root/'command.json'))
    try:
        raw = (root/'command.json').read_bytes()
        record.update(command_sha256=hashlib.sha256(raw).hexdigest(),
                      command=json.loads(raw))
    except (OSError, ValueError) as error:
        record.update(command_read_error=f'{type(error).__name__}: {error}')
    root.mkdir(parents=True, exist_ok=True)
    path = root/'child_outcome.unvalidated.json'
    with path.open('x') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    return path


def successor_checked_runner(parent, abort, check):
    """No launcher: future worker integration must separately be reviewed/pinned."""
    class Runner(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cancel_event = abort

        def _run_test(self, test, image):
            try:
                result = super()._run_test(test, image)
                persist_unvalidated_outcome(result)
                if result.status == 'PASS':
                    check(result)
                    if abort.is_set():
                        result.status, result.reason = 'CANCELLED', 'Abort during validation'
                if result.status != 'PASS':
                    abort.set()
                return result
            except BaseException:
                abort.set()
                raise
    return Runner
