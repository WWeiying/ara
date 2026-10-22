#!/usr/bin/env python3
"""Keep one existing systemd object referenced; record facts, never DUT PASS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
import time
import dbus

HERE = Path(__file__).resolve().parent
UNIT = 'ara-indexed-overlap-m6-01.service'
PLAN = HERE.parent / 'repair06_worker/prepared01/plan.json'
PLAN_SHA = 'd2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8'
INVOCATION = '94f592605b7147d3b5e47923457f3078'
GROUP = '/user.slice/user-1002.slice/user@1002.service/app.slice/' + UNIT
FOLLOWUP = HERE.parent / 'repair06_followup/fresh02/complete.json'


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


class Bus:
    def __init__(self):
        self.connection = dbus.bus.BusConnection('unix:path=/run/user/%d/bus' % os.getuid())
        self.manager = dbus.Interface(self.connection.get_object(
            'org.freedesktop.systemd1', '/org/freedesktop/systemd1'),
            'org.freedesktop.systemd1.Manager')

    def ref(self, unit):
        self.manager.RefUnit(unit, timeout=10)

    def unref(self, unit):
        self.manager.UnrefUnit(unit, timeout=10)

    def close(self):
        self.connection.close()

    def facts(self, unit):
        path = self.manager.GetUnit(unit, timeout=10)
        props = dbus.Interface(self.connection.get_object('org.freedesktop.systemd1', path),
                               'org.freedesktop.DBus.Properties')
        u = props.GetAll('org.freedesktop.systemd1.Unit', timeout=10)
        s = props.GetAll('org.freedesktop.systemd1.Service', timeout=10)
        data = {k: str(u[k]) for k in ('Id', 'LoadState', 'ActiveState', 'SubState')}
        data.update({k: int(s[k]) for k in ('MainPID', 'ExecMainPID', 'ExecMainCode',
                     'ExecMainStatus', 'ExecMainStartTimestamp', 'ExecMainExitTimestamp')})
        data.update(ControlGroup=str(s['ControlGroup']), Result=str(s['Result']),
                    InvocationID=bytes(u['InvocationID']).hex(), observed_unix=time.time())
        return data


def terminal(data):
    return data['ActiveState'] in ('inactive', 'failed') and data['MainPID'] == 0


def identity(data):
    if not (data['Id'] == UNIT and data['LoadState'] == 'loaded' and
            data['InvocationID'] == INVOCATION):
        raise RuntimeError('Unit identity/reload mismatch')


def observe(bus, out, stop, budget=18000, interval=120):
    start = time.monotonic()
    referenced = False
    try:
        initial = bus.facts(UNIT)
        identity(initial)
        if not (initial['ActiveState'] == 'active' and initial['MainPID'] == 620452
                and initial['ControlGroup'] == GROUP):
            raise RuntimeError('Expected original running owner; refuse collected/restarted unit')
        # The second identity check closes the GetUnit/RefUnit exit/reload race.
        bus.ref(UNIT)
        referenced = True
        current = bus.facts(UNIT)
        identity(current)
        save(out / 'startup.json', dict(before=initial, after_ref=current, plan=str(PLAN),
                                       plan_sha256=PLAN_SHA, budget_s=budget, interval_s=interval))
        recorded = False
        while not stop.is_set() and time.monotonic() - start < budget:
            identity(current)
            if terminal(current) and not recorded:
                save(out / 'actualexit.json', dict(kind='SYSTEMD_EXIT_FACTS_ONLY', properties=current,
                     exit_evidence_complete=bool(current['ExecMainCode'] != 0 and
                                                current['ExecMainExitTimestamp'] > 0)))
                recorded = True
            if recorded and FOLLOWUP.is_file():
                save(out / 'release.json', dict(reason='followup_terminal_file_present',
                     followup=str(FOLLOWUP), functional_verdict='NOT_EVALUATED'))
                return
            stop.wait(min(interval, max(0, budget - (time.monotonic() - start))))
            if not stop.is_set() and time.monotonic() - start < budget:
                current = bus.facts(UNIT)
        save(out / 'release.json', dict(reason='signal' if stop.is_set() else 'hold_budget_expired',
                                       actualexit_recorded=recorded))
    finally:
        try:
            if referenced:
                bus.unref(UNIT)
        finally:
            bus.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--authorize-refunit', action='store_true')
    args = parser.parse_args()
    if not args.authorize_refunit:
        parser.error('parent review and --authorize-refunit required')
    if hashlib.sha256(PLAN.read_bytes()).hexdigest() != PLAN_SHA:
        raise RuntimeError('Pinned plan drift')
    out = args.out.resolve()
    if out.parent != HERE:
        raise RuntimeError('Only fresh owned direct output')
    out.mkdir(exist_ok=False)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        observe(Bus(), out, stop)
    except BaseException as error:
        save(out / 'error.json', dict(error=repr(error), functional_verdict='NOT_EVALUATED'))
        raise


if __name__ == '__main__':
    main()
