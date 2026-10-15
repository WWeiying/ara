"""Authorized harmless exit0/exit7 services only; never references the DUT."""
import os
import subprocess
import time
import witness as w


def main():
    out = w.HERE / 'demo01'
    out.mkdir(exist_ok=False)
    env = dict(os.environ, XDG_RUNTIME_DIR='/run/user/%d' % os.getuid(),
               DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/%d/bus' % os.getuid())
    for status in (0, 7):
        unit = 'ara-refunit-demo-%d-%d.service' % (os.getpid(), status)
        bus = w.Bus()
        referenced = False
        try:
            subprocess.run(['systemd-run', '--user', '--unit=' + unit, '--collect',
                            '--property=RuntimeMaxSec=20', '--property=KillMode=control-group',
                            '/bin/sh', '-c', 'sleep 3; exit %d' % status], env=env, check=True)
            bus.ref(unit)
            referenced = True
            start = bus.facts(unit)
            deadline = time.monotonic() + 30
            while True:
                facts = bus.facts(unit)
                if w.terminal(facts):
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('demo deadline')
                time.sleep(1)
            time.sleep(2)
            retained = bus.facts(unit)
            assert retained['LoadState'] == 'loaded'
            assert retained['ExecMainCode'] == 1 and retained['ExecMainStatus'] == status
            assert retained['ExecMainExitTimestamp'] > retained['ExecMainStartTimestamp'] > 0
            w.save(out / ('exit%d.json' % status), dict(unit=unit, startup=start,
                   retained_after_exit=retained, kind='HARMLESS_DEMO_NOT_DUT'))
        finally:
            # Deliberately close without UnrefUnit: prove connection ownership release.
            bus.close()
        probe = w.Bus()
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    probe.facts(unit)
                except w.dbus.DBusException as error:
                    if error.get_dbus_name() != 'org.freedesktop.systemd1.NoSuchUnit':
                        raise
                    w.save(out / ('released%d.json' % status), dict(unit=unit,
                           after_connection_close=error.get_dbus_name()))
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('demo not collected after connection close')
                time.sleep(1)
        finally:
            probe.close()


if __name__ == '__main__':
    main()
