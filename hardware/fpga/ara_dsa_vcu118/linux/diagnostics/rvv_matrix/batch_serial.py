"""Observe a preloaded guest batch; never upload, interrupt, or reset the board.

The recovery wrapper must own the campaign lock and confirm a guest shell before
calling this adapter. A single hash-checked command replaces per-case commands.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from guest_batch import script
from guest_watch import Watch


class SnapshotCleanupRace(RuntimeError):
    pass


def cleanup_race_report(target):
    try:
        report = json.loads((target/'report.json').read_text())
        json.loads((target/'snapshot.json').read_text())
    except (OSError, ValueError):
        return False
    return (report.get('command') == 'snapshot' and report.get('state') == 'failed'
            and isinstance(report.get('error'), str)
            and report['error'].startswith('Owned Vivado tree cleanup failed:'))


def collect_snapshot_pair(capture):
    # Retry the whole pair so the last two archived captures are both successful.
    for attempt in range(2):
        try:
            return [capture(), capture()]
        except SnapshotCleanupRace:
            if attempt:
                raise


def save_report(path, report, replace=os.replace, sleep=time.sleep):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    # Windows readers can briefly deny replacement without FILE_SHARE_DELETE.
    for attempt in range(51):
        try:
            replace(temporary, path)
            return
        except PermissionError:
            if attempt == 50:
                raise
            sleep(.1)


def command(directory, script_hash):
    if not re.fullmatch(r'/tmp/width_[0-9a-f]{12}', directory):
        raise ValueError('Invalid preloaded guest directory')
    if not re.fullmatch(r'[0-9a-f]{64}', script_hash):
        raise ValueError('Invalid script hash')
    return (f'cd {directory} && actual=$(sha256sum batch.sh) && '
            'actual=${actual%% *} && test "$actual" = '
            f'{script_hash} && sh ./batch.sh\n').encode('ascii')


def verify(root):
    manifest = json.loads((root/'transfer_manifest.json').read_text())
    protocol = json.loads((root/'batch_protocol.json').read_text())
    content = (root/'batch.sh').read_bytes()
    if (protocol['inputs'] != manifest or
            hashlib.sha256(content).hexdigest() != protocol['script_sha256'] or
            content != script(manifest, protocol['run_id']).encode('utf-8')):
        raise ValueError('Batch script, manifest or protocol identity differs')
    return manifest, protocol


def observe(port, manifest, run_id, launch, log, save, snapshots,
            now=time.monotonic, sleep=time.sleep):
    def drain(watch):
        for _ in range(64):
            if watch.terminal:
                return
            chunk = port.read(4096)
            if not chunk:
                return
            log.write(chunk)
            log.flush()
            watch.feed(chunk, now())
    watch = Watch(manifest, run_id, now(), snapshots, drain=drain)
    save(watch.report)
    saved_at = now()
    saved_key = None
    try:
        # Only the short launch command is paced; the guest executes every case locally.
        for byte in launch:
            if port.write(bytes([byte])) != 1:
                raise OSError('Incomplete serial command write')
            sleep(.02)
        watch.started = now()
        while not watch.terminal:
            chunk = port.read(4096)
            if chunk:
                log.write(chunk)
                log.flush()
                watch.feed(chunk, now())
            watch.tick(now())
            key = (watch.report['state'], len(watch.report['results']), watch.terminal)
            if key != saved_key or now()-saved_at >= 2:
                save(watch.report)
                saved_key, saved_at = key, now()
    except Exception as exc:
        watch.fail('Serial observation failed; no interrupt or reset sent: '+str(exc))
    finally:
        save(watch.report)
    return watch.report


def main(args):
    manifest, protocol = verify(args.root)
    launch = command(args.guest_directory, protocol['script_sha256'])
    sys.path.insert(0, str(args.host_tools))
    import host_load
    # Refuse to overwrite a prior UART scene or attach after a prior observer attempt.
    if (args.root/'report.json').exists():
        raise ValueError('Observer report already exists')
    with (args.root/'batch_uart.bin').open('xb') as log:
        def save(report):
            save_report(args.root/'report.json', report)
        sample_index = 0
        def capture():
            nonlocal sample_index
            sample_index += 1
            target = args.root/f'batch_progress_{sample_index:04d}'
            result = subprocess.run([sys.executable, str(Path(host_load.__file__)),
                'snapshot', '--out', str(target), '--probes', str(args.probes),
                '--vivado', str(args.vivado)], capture_output=True, timeout=180,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                if cleanup_race_report(target):
                    raise SnapshotCleanupRace('Progress snapshot cleanup failed; scene preserved')
                raise RuntimeError('Progress snapshot failed; scene preserved')
            return json.loads((target/'snapshot.json').read_text())
        def snapshots():
            return collect_snapshot_pair(capture)
        with host_load.serial_module().Serial(args.port, 115200, timeout=.2, write_timeout=5) as port:
            report = observe(port, manifest, protocol['run_id'], launch, log, save, snapshots)
    return 0 if report['state'] == 'all_cases_finished_review_results' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--guest-directory', required=True)
    parser.add_argument('--host-tools', type=Path, required=True)
    parser.add_argument('--probes', type=Path, required=True)
    parser.add_argument('--vivado', type=Path, required=True)
    parser.add_argument('--port', default='COM6')
    raise SystemExit(main(parser.parse_args()))
