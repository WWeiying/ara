"""One offline successor after the recorded old parser timeout; never runs Spike."""
from pathlib import Path
import sys

OWN = Path(__file__).resolve().parent
sys.path.insert(0, str(OWN.parent))
from prepare import read, save, sha, require, pins_check, command

OLD_BOUND = 'bfc5d224fb820f354ee11bc04c779f21093dbdece6baf22ef20a2d6da96bc0b6'
RAW = OWN.parent / 'reference01/commits.log'


def identity():
    s = RAW.stat()
    return dict(path=str(RAW), device=s.st_dev, inode=s.st_ino, size=s.st_size,
                mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def prerequisite():
    old = OWN.parent / 'reference01'
    require(sha(OWN.parent / 'reference_bound01.json') == OLD_BOUND, 'Old bound changed')
    receipt = read(old / 'audit.log.exit.json')
    require(receipt['timeout'] is True and receipt['returncode'] == -9 and
            receipt['attempts'] == 1, 'Successor allowed only after actual old timeout')
    spike = read(old / 'spike.stdout.exit.json')
    require(spike['returncode'] == 0 and not spike['timeout'] and spike['attempts'] == 1,
            'Original actual Spike exit')
    require(not (old / 'reference.json').exists(), 'Do not repeat completed old full audit')
    require(read(old / 'NOT_ACCEPTED.json')['status'] == 'NOT_ACCEPTED_NO_RETRY', 'Old record')


def host():
    command([sys.executable, '-B', OWN / 'test_cache.py'], OWN / 'host.log', 30)


def freeze():
    prerequisite()
    host_exit = read(OWN / 'host.log.exit.json')
    require(host_exit['returncode'] == 0 and not host_exit['timeout'], 'Actual Host exit')
    pins = dict(read(OWN.parent / 'reference_bound01.json')['pins'])
    for p in [OWN.parent / 'reference_bound01.json',
              *[OWN / n for n in ('audit.py', 'completion_cache.py', 'test_cache.py', 'run.py',
                                  'host.log', 'host.log.command.json', 'host.log.exit.json')],
              *[OWN.parent / 'reference01' / n for n in
                ('spike.stdout.exit.json', 'audit.log.exit.json', 'NOT_ACCEPTED.json')]]:
        pins[str(p)] = sha(p)
    pins_check(pins)
    save(OWN / 'bound.json', dict(pins=pins, raw_identity=identity(), old_bound=OLD_BOUND,
                                 seconds=600, offline_only=True, attempts=1))
    print(sha(OWN / 'bound.json'), flush=True)


def run(digest):
    require(sha(OWN / 'bound.json') == digest, 'Successor bound')
    b = read(OWN / 'bound.json'); prerequisite(); pins_check(b['pins'])
    require(identity() == b['raw_identity'], 'Closed raw identity before')
    out = OWN / 'run01'; out.mkdir()
    try:
        receipt = command([sys.executable, '-B', OWN / 'audit.py', '--bound-sha256', OLD_BOUND],
                          out / 'audit.log', 600)
        pins_check(b['pins']); require(identity() == b['raw_identity'], 'Closed raw identity after')
        result = read(out / 'reference.json')
        require(result['status'] == 'FULL_ORIGINAL1134_REFERENCE_PASS_NOT_DUT', 'Audit status')
        save(out / 'RESULT.json', dict(status='FULL1134_O2_OFFLINE_SUCCESSOR_PASS_NOT_DUT',
             actual_audit=receipt, bound_sha256=digest, reference_sha256=sha(out / 'reference.json'),
             firmware_through_htif=result['firmware_through_htif'],
             original_spike_receipt=read(OWN.parent / 'reference01/spike.stdout.exit.json'),
             old_timeout_retained=True, spike_reruns=0, DUT_started=False))
        print('OFFLINE_PASS', result['firmware_through_htif'], flush=True)
    except BaseException as error:
        save(out / 'NOT_ACCEPTED.json', dict(status='NOT_ACCEPTED_NO_RETRY', error=str(error)))
        raise


if __name__ == '__main__':
    if sys.argv[1:] == ['host']:
        host()
    elif sys.argv[1:] == ['freeze']:
        freeze()
    else:
        require(len(sys.argv) == 3 and sys.argv[1] == 'run', 'Explicit one-shot mode/bound')
        run(sys.argv[2])
