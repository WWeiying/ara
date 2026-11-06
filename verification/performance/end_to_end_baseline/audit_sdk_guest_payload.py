#!/usr/bin/env python3
"""Independent newc/ELF payload audit; never executes or accepts a model run."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys


HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[2]
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
WORKER = RUNS / 'e2e_sdk_dispatch_model_pair_20261106_01'
PRIOR = RUNS / 'e2e_trace_context_model_pair_20261106_01'
LIBRARY = RUNS / 'e2e_sdk_dispatch_library_20261106_01/attempt-02'
OUT = RUNS / 'e2e_sdk_dispatch_payload_audit_20261106_01'
RECEIPT = MAIN / 'verification/performance/evidence/trace_context_model_20261106_01/result.json'
RECEIPT_SHA = 'c0079fe778bbd4b69de8cfa57dc128add6e06125212222b4837ddc00d5124024'
PRIOR_RESULT_SHA = '74d04aece83a5c78764434bbde7d219aeef18ede0c5919f35ed0450654301ab5'
PRODUCER_SHA = 'abc847330267ef8a6cc794b413f0f5067eded89846ce9c74a73fa971c1135653'
LIBRARY_SHA = 'd335a23205c19f0f4e4e8e77b4160812a925b3e848cb967b4479b0a6f4d29c5f'
OWNED = ('audit_sdk_guest_payload.py', 'test_sdk_guest_payload.py')
SUCCESS = 'SDK_DISPATCH_GUEST_PAYLOAD_ONLY_AUDIT_PASS'
EXPECTED_MODES = {'dev': stat.S_IFDIR | 0o755, 'dev/console': stat.S_IFCHR | 0o600,
                  'model': stat.S_IFDIR | 0o755, 'tmp': stat.S_IFDIR | 0o1777,
                  **{name: stat.S_IFREG | 0o755 for name in ('init', 'base', 'candidate', 'test')}}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''):
            h.update(data)
    return h.hexdigest()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def parse_newc(data):
    """Parse one canonical relative-name archive, without extracting anything."""
    require(isinstance(data, bytes), 'Expected archive bytes')
    offset, entries, inodes = 0, {}, set()
    while True:
        require(offset % 4 == 0 and offset + 110 <= len(data), 'Unaligned/truncated newc header or missing trailer')
        header_offset = offset
        header = data[offset:offset + 110]
        require(header[:6] in (b'070701', b'070702') and
                re.fullmatch(rb'[0-9a-fA-F]{104}', header[6:]) is not None, 'Invalid newc magic/hex header')
        fields = [int(header[i:i + 8], 16) for i in range(6, 110, 8)]
        ino, mode, uid, gid, links, mtime, size, major, minor, rmajor, rminor, namesize, check = fields
        offset += 110
        require(1 < namesize <= 4096 and offset + namesize <= len(data), 'Invalid/truncated name length')
        name_bytes = data[offset:offset + namesize]
        require(name_bytes[-1:] == b'\0' and b'\0' not in name_bytes[:-1], 'Name must have exactly one final NUL')
        require(all(33 <= b <= 126 for b in name_bytes[:-1]), 'Noncanonical name bytes')
        name = name_bytes[:-1].decode('ascii')
        require(not name.startswith('/') and '\\' not in name and
                all(part not in ('', '.', '..') for part in name.split('/')), 'Unsafe path/traversal')
        offset += namesize
        aligned = (offset + 3) & ~3
        require(aligned <= len(data) and not any(data[offset:aligned]), 'Invalid name alignment padding')
        offset = aligned
        require(offset + size <= len(data), 'Truncated payload')
        payload = data[offset:offset + size]
        offset += size
        aligned = (offset + 3) & ~3
        require(aligned <= len(data) and not any(data[offset:aligned]), 'Invalid payload alignment padding')
        offset = aligned
        require(check == (sum(payload) & 0xffffffff if header[:6] == b'070702' else 0), 'Invalid newc checksum')
        if name == 'TRAILER!!!':
            require(fields == [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 11, 0], 'Malformed trailer')
            require(not any(data[offset:]), 'Only NUL padding allowed after trailer')
            return entries, dict(trailer_offset=header_offset, trailing_nul_bytes=len(data) - offset,
                                 archive_bytes=len(data))
        require(name not in entries, 'Duplicate archive name: ' + name)
        identity = (major, minor, ino)
        require(identity not in inodes, 'Duplicate inode/hardlink alias')
        inodes.add(identity)
        entries[name] = dict(mode=mode, uid=uid, gid=gid, nlink=links, mtime=mtime,
                             rdevmajor=rmajor, rdevminor=rminor, data=payload,
                             header_offset=header_offset, magic=header[:6].decode())


def elf64_riscv(data):
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01' and
            struct.unpack_from('<HHI', data, 16) == (2, 243, 1) and
            struct.unpack_from('<H', data, 52)[0] == 64, 'Expected little-endian RV64 executable ELF')


def validate_payload(data, expected):
    require(set(expected) == {'init', 'base', 'candidate', 'test'}, 'Wrong expected executable set')
    require(expected['base'] != expected['candidate'], 'A/A baseline/candidate payload')
    entries, layout = parse_newc(data)
    require(set(entries) == set(EXPECTED_MODES), 'Unexpected/missing archive entry set')
    for name, entry in entries.items():
        require(entry['mode'] == EXPECTED_MODES[name] and entry['uid'] == entry['gid'] == 0,
                'Wrong mode/owner: /' + name)
        regular = name in expected
        require(entry['nlink'] == (2 if stat.S_ISDIR(entry['mode']) else 1), 'Unexpected hardlinks')
        require((entry['rdevmajor'], entry['rdevminor']) == ((5, 1) if name == 'dev/console' else (0, 0)),
                'Wrong device identity: /' + name)
        if regular:
            require(entry['data'] == expected[name], 'Guest executable bytes differ: /' + name)
            elf64_riscv(entry['data'])
        else:
            require(not entry['data'], 'Nonempty directory/device payload')
    require(entries['base']['data'] != entries['candidate']['data'], 'A/A archive payload')
    return dict(layout=layout, entries={('/' + name): {
        **{key: value for key, value in entry.items() if key != 'data'},
        'bytes': len(entry['data']), 'sha256': sha(entry['data'])} for name, entry in entries.items()})


class Pins:
    def __init__(self):
        self.values, self.identities = {}, {}

    def pin(self, path, expected=None):
        lexical = Path(path).absolute()
        path = lexical.resolve(strict=True)
        require(path.is_file(), 'Not a regular input: ' + str(path))
        actual = digest(path)
        require(expected is None or actual == expected, 'Identity mismatch: ' + str(path))
        require(str(path) not in self.values or self.values[str(path)] == actual, 'Input drift: ' + str(path))
        self.values[str(path)] = actual
        self.identities[str(lexical)] = str(path)
        return actual

    def verify(self):
        for name, target in self.identities.items():
            require(str(Path(name).resolve(strict=True)) == target, 'Symlink drift: ' + name)
        for name, expected in self.values.items():
            require(digest(name) == expected, 'Final input drift: ' + name)


def pinned_input(pins, inventory, path, expected=None):
    path = Path(path)
    key = str(path.resolve(strict=True))
    require(key in inventory and re.fullmatch('[0-9a-f]{64}', inventory[key]) is not None,
            'Consumed input absent from worker pins: ' + key)
    require(expected is None or expected == inventory[key], 'Accepted identity disagrees with worker pin: ' + key)
    return pins.pin(path, inventory[key])


def one(records, label):
    matches = [row for row in records if row['label'] == label]
    require(len(matches) == 1, 'Missing/duplicate command: ' + label)
    return matches[0]


def expected_link(original, model, baseline, candidate, old_output, new_output):
    require(all(original.count(str(value)) == 1 for value in (model, baseline, old_output)) and
            original.count('-o') == 1 and '-static' in original, 'Ambiguous/nonstatic accepted link')
    position = original.index('-o') + 1
    require(position < len(original) and original[position] == str(old_output), 'Wrong accepted link output')
    return [str(candidate) if value == str(baseline) else str(new_output) if i == position else value
            for i, value in enumerate(original)]


def validate_link(records, expected, root):
    row = one(records, 'link-candidate')
    require(row['argv'] == expected and row.get('returncode') == 0 and row['cwd'] == str(root),
            'Candidate link command/returncode/cwd differs')


def observe(path, output, label, pins):
    data = Path(path).read_bytes()
    value = json.loads(data)
    snapshot = output / (label + '.json')
    with snapshot.open('xb') as stream:
        stream.write(data)
    pins.pin(snapshot, sha(data))
    return value, dict(path=str(path), snapshot=str(snapshot), sha256=sha(data))


def ownership():
    observations = []
    for name in ('e2e_sdk_dispatch_model_pair_20261106_01', 'e2e_sdk_dispatch_model_campaign_20261106_01',
                 'e2e_rms_norm_vcs_20261106_01', 'e2e_sdk_single_input_vcs_20261106_01'):
        path = RUNS / name / 'source-pins.json'
        data = path.read_bytes()
        inventory = json.loads(data)
        conflicts = [str(HERE / n) for n in OWNED if str(HERE / n) in inventory]
        require(not conflicts, 'New helper already sealed by worker: ' + repr(conflicts))
        observations.append(dict(path=str(path), sha256=sha(data), entries=len(inventory),
                                 owned_conflicts=conflicts, inherited_documentation={
                                     k: v for k, v in inventory.items() if Path(k).suffix.lower() in ('.md', '.markdown')}))
    return observations


def audit(output):
    output = Path(output).absolute()
    require(output == OUT and output.resolve() == OUT, 'Only assigned fresh audit output allowed')
    inventory_observations = ownership()
    output.mkdir(exist_ok=False)
    pins = Pins()
    result = dict(state='SDK_DISPATCH_GUEST_PAYLOAD_ONLY_AUDIT_FAIL', payload_only=True,
                  model_functional_pass=False, performance_measured=False, target_executed=False,
                  worker_pass_required=False, worker_modified=False)
    try:
        write_new(output / 'worker-pin-inventory.json', inventory_observations)
        for name in OWNED:
            value = pins.pin(HERE / name)
            snapshot = output / name
            with snapshot.open('xb') as stream:
                stream.write((HERE / name).read_bytes())
            pins.pin(snapshot, value)
        pins.pin(Path(sys.executable).resolve())
        with (output / 'unit-tests.log').open('xb') as log:
            test = subprocess.run([sys.executable, '-B', HERE / OWNED[1]], stdout=log,
                                  stderr=subprocess.STDOUT, timeout=60, check=False)
        require(test.returncode == 0, 'Successor tests failed')
        status, status_observation = observe(WORKER / 'status.json', output, 'worker-status-snapshot', pins)
        worker_pins, pin_observation = observe(WORKER / 'source-pins.json', output, 'worker-pins-snapshot', pins)
        require(pin_observation['sha256'] == status['source_pins_sha256'], 'Status/source-pins snapshot binding')
        commands, command_observation = observe(WORKER / 'commands.json', output, 'worker-commands-snapshot', pins)
        pins.pin(RECEIPT, RECEIPT_SHA)
        receipt = json.loads(RECEIPT.read_text())
        require(receipt['state'] == 'TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED' and
                receipt['worker_result_sha256'] == PRIOR_RESULT_SHA, 'Wrong accepted prior receipt')
        audit_result = Path(receipt['run']) / 'result.json'
        pins.pin(audit_result, receipt['result_sha256'])
        accepted = json.loads(audit_result.read_text())['report']
        require(accepted['run'] == str(PRIOR) and accepted['worker_result_sha256'] == PRIOR_RESULT_SHA,
                'Accepted audit/prior binding')
        pinned_input(pins, worker_pins, PRIOR / 'result.json', PRIOR_RESULT_SHA)
        prior = json.loads((PRIOR / 'result.json').read_text())
        pinned_input(pins, worker_pins, PRIOR / 'source-pins.json', receipt['source_pins_sha256'])
        old = json.loads((PRIOR / 'source-pins.json').read_text())
        for name in ('commands.json', 'initramfs.list', 'model.o', 'candidate', 'test'):
            pinned_input(pins, worker_pins, PRIOR / name, prior['artifacts'][str(PRIOR / name)])
        require(prior['candidate_elf_sha256'] == accepted['candidate_elf_sha256'] and
                prior['common_model_object_sha256'] == accepted['common_model_object_sha256'],
                'Accepted baseline/model object identity')
        for name, field in (('candidate', 'candidate_elf_sha256'), ('model.o', 'common_model_object_sha256'),
                            ('test', 'driver_elf_sha256')):
            require(digest(PRIOR / name) == prior[field], 'Prior ELF/object report mismatch')
        pinned_input(pins, worker_pins, LIBRARY / 'result.json', PRODUCER_SHA)
        producer = json.loads((LIBRARY / 'result.json').read_text())
        require(producer['state'] == 'SDK_DISPATCH_LIBRARY_BUILT_ARCHIVE_VERIFIED' and
                producer['candidate_library_sha256'] == LIBRARY_SHA and
                producer['baseline_library_sha256'] == receipt['candidate_library_sha256'] and
                producer['member'] == 'qbs_runtime.c.o' and producer['changed_members'] == 1 and
                producer['original_object_reproduced_exactly'] is True, 'Wrong accepted archive producer')
        pinned_input(pins, worker_pins, LIBRARY / 'source-pins.json', producer['source_pins_sha256'])
        baseline_library, candidate_library = Path(producer['baseline_library']), Path(producer['candidate_library'])
        require(candidate_library == LIBRARY / 'lib/libggml-cpu.a', 'Wrong candidate archive path')
        pinned_input(pins, worker_pins, baseline_library, receipt['candidate_library_sha256'])
        pinned_input(pins, worker_pins, candidate_library, LIBRARY_SHA)
        pinned_input(pins, worker_pins, producer['candidate_object'], producer['candidate_object_sha256'])
        original_commands = json.loads((PRIOR / 'commands.json').read_text())
        original_link = one(original_commands, 'link-candidate')['argv']
        link = expected_link(original_link, PRIOR / 'model.o', baseline_library, candidate_library,
                             PRIOR / 'candidate', WORKER / 'candidate')
        validate_link(commands, link, WORKER)
        for token in link[:-1]:
            if token.startswith('/'):
                expected = LIBRARY_SHA if token == str(candidate_library) else old[str(Path(token).resolve(strict=True))]
                pinned_input(pins, worker_pins, token, expected)
        require(status['library_build'] == str(LIBRARY) and status['prior_model_worker'] == str(PRIOR) and
                status['candidate_library_sha256'] == LIBRARY_SHA and
                status['baseline_library_sha256'] == receipt['candidate_library_sha256'] and
                status['common_model_object_sha256'] == prior['common_model_object_sha256'] and
                status['baseline_elf_sha256'] == prior['candidate_elf_sha256'] and
                status['driver_elf_sha256'] == prior['driver_elf_sha256'], 'Status contradicts accepted identities')
        pinned_input(pins, worker_pins, WORKER / 'candidate', status['candidate_elf_sha256'])
        reproduced = expected_link(original_link, PRIOR / 'model.o', baseline_library, baseline_library,
                                   PRIOR / 'candidate', WORKER / 'baseline-reproduced')
        reproduction = one(commands, 'link-reproduce-baseline')
        require(reproduction['argv'] == reproduced and reproduction.get('returncode') == 0,
                'Baseline reproduction command binding')
        pinned_input(pins, worker_pins, WORKER / 'baseline-reproduced', prior['candidate_elf_sha256'])
        old_listing = (PRIOR / 'initramfs.list').read_text().splitlines()
        init_rows = [line.split() for line in old_listing if line.startswith('file /init ')]
        require(len(init_rows) == 1 and len(init_rows[0]) == 6, 'Accepted init mapping')
        init = Path(init_rows[0][2])
        pinned_input(pins, worker_pins, init, old[str(init.resolve(strict=True))])
        targets = dict(init=init, base=PRIOR / 'candidate', candidate=WORKER / 'candidate', test=PRIOR / 'test')
        payloads = {}
        for name, path in targets.items():
            require(stat.S_ISREG(path.stat().st_mode) and path.stat().st_mode & 0o111, 'Nonexecutable host target')
            pinned_input(pins, worker_pins, path)
            payloads[name] = path.read_bytes()
            require(sha(payloads[name]) == pins.values[str(path.resolve())], 'Target read drift')
        image = WORKER / 'initramfs.cpio'
        pinned_input(pins, worker_pins, image)
        cpio = image.read_bytes()
        require(sha(cpio) == pins.values[str(image)], 'Archive read drift')
        contents = validate_payload(cpio, payloads)
        listing = ('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
                   'dir /model 755 0 0\ndir /tmp 1777 0 0\n' +
                   ''.join(f'file /{name} {path} 755 0 0\n' for name, path in targets.items()))
        pinned_input(pins, worker_pins, WORKER / 'initramfs.list')
        require((WORKER / 'initramfs.list').read_text() == listing, 'Worker listing differs from actual/accepted mapping')
        make = one(commands, 'make-initramfs')
        require(make['argv'][1:] == [str(WORKER / 'initramfs.list')] and make.get('returncode') == 0,
                'Archive generator command binding')
        pinned_input(pins, worker_pins, make['argv'][0], old[str(Path(make['argv'][0]).resolve())])
        original_qemu = one(original_commands, 'qemu')['argv']
        require(original_qemu.count('-initrd') == 1, 'Ambiguous original initrd')
        qemu = list(original_qemu)
        qemu[qemu.index('-initrd') + 1] = str(image)
        require(one(commands, 'qemu')['argv'] == qemu, 'Actual QEMU/model configuration differs from acceptance')
        disk = Path(qemu[qemu.index('-drive') + 1].split(',', 1)[0].removeprefix('file='))
        require('readonly=on' in qemu[qemu.index('-drive') + 1], 'Model disk must remain read-only')
        pinned_input(pins, worker_pins, disk, old[str(disk.resolve())])
        pins.verify()
        # Recheck only immutable consumed evidence, not status or a pending qemu returncode.
        current_pins = json.loads((WORKER / 'source-pins.json').read_text())
        require(all(current_pins.get(name) == value for name, value in worker_pins.items()
                    if name in pins.values), 'Consumed worker pins changed during audit')
        validate_link(json.loads((WORKER / 'commands.json').read_text()), link, WORKER)
        write_new(output / 'payloads.json', contents)
        result.update(state=SUCCESS, post_pins_match=True, worker_state_observed=status.get('state'),
                      cpio_sha256=sha(cpio), payload_sha256={('/' + k): sha(v) for k, v in payloads.items()},
                      observations=[status_observation, pin_observation, command_observation],
                      accepted_prior_result_sha256=PRIOR_RESULT_SHA, producer_result_sha256=PRODUCER_SHA,
                      candidate_library_sha256=LIBRARY_SHA, model_disk_sha256=old[str(disk.resolve())],
                      link_command_verified=True, exact_guest_entry_set_verified=True, base_candidate_distinct=True,
                      limitations=['Payload and recorded link provenance only; not a model functional PASS or performance acceptance',
                                   'No native replay, relink, QEMU, VCS, synthesis, or worker modification',
                                   'Mutable status/commands retained as snapshots; no worker PASS requirement'])
    except Exception as exc:
        result.update(error=repr(exc), post_pins_match=False)
    write_new(output / 'source-pins.json', pins.values)
    write_new(output / 'path-identities.json', pins.identities)
    result['source_pins_sha256'] = digest(output / 'source-pins.json')
    result['artifacts'] = {str(path): digest(path) for path in sorted(output.iterdir()) if path.is_file()}
    write_new(output / 'result.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args(argv)
    result = audit(args.output)
    print(json.dumps(result, indent=2))
    return 0 if result['state'] == SUCCESS else 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
