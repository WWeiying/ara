#!/usr/bin/env python3
"""Host snapshot tests, including the real PAM metadata; never start simulation."""
from pathlib import Path
import sys
import tempfile
from unittest import mock

sys.dont_write_bytecode = True
import successor_snapshot03 as s


def main():
    negatives = []
    def reject(name, fn):
        try:
            fn()
        except ValueError:
            negatives.append(name)
        else:
            raise AssertionError('Invalid process accepted: ' + name)

    pam = Path('/proc/624598')
    comm = (pam / 'comm').read_text().strip()
    groups = [x.split(':', 2)[2] for x in (pam / 'cgroup').read_text().splitlines()]
    argv = (pam / 'cmdline').read_bytes().decode(errors='replace').split('\0')
    assert comm == '(sd-pam)' and groups == ['/user.slice/user-1002.slice/user@1002.service/init.scope']
    assert not s.relevant(comm, groups, argv)
    real_resolve = Path.resolve
    accessed = []
    def deny_pam(path, *args, **kwargs):
        if path in (pam / 'exe', pam / 'cwd'):
            accessed.append(str(path))
            raise PermissionError('nondumpable PAM')
        return real_resolve(path, *args, **kwargs)
    with mock.patch.object(Path, 'resolve', deny_pam):
        assert s.inspect_process(pam) is None
    assert not accessed
    with tempfile.TemporaryDirectory(prefix='snapshot03-host-', dir=s.HERE) as temporary:
        root = Path(temporary) / '12345'
        root.mkdir()
        def metadata(comm, groups, argv):
            (root / 'comm').write_text(comm + '\n')
            (root / 'stat').write_text('12345 (' + comm + ') S ' + ' '.join(['0'] * 19))
            (root / 'cgroup').write_text('0::' + groups + '\n')
            (root / 'cmdline').write_bytes('\0'.join(argv).encode())
        def deny(path, *args, **kwargs):
            if path in (root / 'exe', root / 'cwd'):
                raise PermissionError('synthetic relevant process')
            return real_resolve(path, *args, **kwargs)
        with mock.patch.object(Path, 'resolve', deny):
            metadata('(sd-pam)', groups[0], argv)
            assert s.inspect_process(root) is None
            for name, proccomm, group, args in [
                ('simv_exe_denied', 'simv', '/elsewhere', ['simv']),
                ('simv_argv_denied', 'renamed', '/elsewhere', ['/image/simv']),
                ('NF2_cgroup_denied', 'python3', '/slice/' + s.gate.NF2_UNIT, []),
                ('arithmetic_cgroup_denied', 'python3', '/slice/' + s.gate.ARITH_UNIT, []),
                ('NF2_argv_denied', 'python3', '/elsewhere', [str(s.gate.NF2.parent / 'vcs_adapter.py')]),
                ('arithmetic_argv_denied', 'python3', '/elsewhere', ['--out=' + str(s.gate.ARITH)])]:
                metadata(proccomm, group, args)
                reject(name, lambda: s.inspect_process(root))
        metadata('simv', '/elsewhere', ['simv'])
        def deny_cwd(path, *args, **kwargs):
            if path == root / 'exe':
                return Path('/image/simv')
            if path == root / 'cwd':
                raise PermissionError('cwd denied')
            return real_resolve(path, *args, **kwargs)
        with mock.patch.object(Path, 'resolve', deny_cwd):
            reject('simv_cwd_denied', lambda: s.inspect_process(root))
        read_bytes = Path.read_bytes
        def deny_cmdline(path):
            if path == root / 'cmdline':
                raise PermissionError('cannot classify')
            return read_bytes(path)
        metadata('(sd-pam)', groups[0], [])
        with mock.patch.object(Path, 'read_bytes', deny_cmdline):
            reject('unclassifiable_metadata_denied', lambda: s.inspect_process(root))
    s.gate.save(s.HERE / 'snapshot03_host_tests.json', dict(status='HOST_SNAPSHOT03_PASS_NOT_DUT',
        negatives=negatives, real_PAM_pid=624598, real_PAM_comm=comm, real_PAM_cgroups=groups,
        real_PAM_argv=argv, PAM_exe_cwd_accesses=accessed, VCS_started=False,
        pins=s.gate.pins([Path(__file__), Path(s.__file__), Path(s.gate.__file__)])))
    print('HOST_SNAPSHOT03_PASS_NOT_DUT', len(negatives), 'real PAM ignored without exe/cwd access')


if __name__ == '__main__':
    main()
