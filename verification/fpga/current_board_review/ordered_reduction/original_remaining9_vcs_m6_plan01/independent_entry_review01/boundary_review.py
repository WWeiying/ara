#!/usr/bin/env python3
"""Real Timer/Event and real process-signal boundaries; no pending-set mocks."""
import dis
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent))
import replay
common = replay.common
code = common.publish.__code__
ops = list(dis.get_instructions(common.publish))
queries = [i for i, op in enumerate(ops) if op.argval == 'sigpending']
assert len(queries) == 2
before = ops[queries[-1]].offset
call_index = next(i for i in range(queries[-1], len(ops)) if ops[i].opname.startswith('CALL'))
after = ops[call_index+1].offset

def publish_at(name, abort, offset=None, action=None):
    out = OUT/name
    out.mkdir()
    hit = False
    def tracer(frame, event, arg):
        nonlocal hit
        if frame.f_code is code:
            frame.f_trace_opcodes = True
            if event == 'opcode' and frame.f_lasti == offset and not hit:
                hit = True
                action()
            return tracer
    terminal = dict(status=replay.PASS)
    with common.abort_signals(abort):
        sys.settrace(tracer)
        try:
            common.publish(out, terminal, abort)
        finally:
            sys.settrace(None)
    if offset is not None:
        assert hit
    result = common.read(out/'complete.json')
    return dict(name=name, terminal=result, event_after_publish=abort.is_set())

def main():
    results = []
    # Repeat the old race using the real sigpending syscall and an actual Timer.
    abort, release, fired = threading.Event(), threading.Event(), threading.Event()
    def callback():
        assert release.wait(5)
        abort.set()
        fired.set()
    timer = threading.Timer(0, callback)
    timer.start()
    def trigger():
        release.set()
        assert fired.wait(5)
    try:
        r = publish_at('old_real_timer_race', abort, before, trigger)
    finally:
        release.set()
        timer.join()
    assert r['event_after_publish'] and r['terminal']['status'] == replay.PASS
    results.append(r)

    # Quiescing joins an already running callback and preserves its sticky abort.
    abort, entered, release = threading.Event(), threading.Event(), threading.Event()
    def callback2():
        entered.set()
        assert release.wait(5)
        abort.set()
    timer = threading.Timer(0, callback2)
    timer.start()
    assert entered.wait(5)
    releaser = threading.Timer(.02, release.set)
    releaser.start()
    replay.quiesce_deadline(timer, abort, time.monotonic()+100)
    releaser.join()
    assert not timer.is_alive() and abort.is_set()
    r = publish_at('fixed_joined_timer', abort)
    assert r['terminal']['status'] == 'NOT_PASS' and r['terminal']['aborted']
    results.append(r)

    abort = threading.Event()
    timer = threading.Timer(100, abort.set)
    timer.start()
    replay.quiesce_deadline(timer, abort, time.monotonic()-1)
    r = publish_at('fixed_expired_deadline', abort)
    assert r['terminal']['status'] == 'NOT_PASS'
    results.append(r)

    assert threading.active_count() == 1
    # Kernel snapshot is the final signal decision, not rename/Python return.
    for number in (signal.SIGINT, signal.SIGTERM):
        for where, offset, expected in [('before', before, 'NOT_PASS'), ('after', after, replay.PASS)]:
            abort = threading.Event()
            r = publish_at(f'{number.name}_{where}_snapshot', abort, offset, lambda: os.kill(os.getpid(), number))
            assert r['terminal']['status'] == expected, r
            assert r['event_after_publish']
            results.append(r)
    evidence = dict(status='PASS_HOST_BOUNDARY_ONLY', cases=results,
        real_sigpending=True, real_Timer=True, real_process_signals=True,
        decision='Final kernel pending-set snapshot after joined workers and Timer; post-snapshot signals do not revoke acceptance',
        DUT_started=False, live_queries=False)
    (OUT/'boundary_evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(dict(status=evidence['status'], cases=len(results))))

if __name__ == '__main__':
    main()
