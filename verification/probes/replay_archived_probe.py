#!/usr/bin/env python3
"""Replay one frozen failure with existing probes and a bounded no-progress watchdog."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--probe', action='append', default=[])
    ap.add_argument('--watchdog', type=int, default=3000)
    args = ap.parse_args()
    source = args.case.resolve(strict=True)
    output = args.output.resolve()
    original = json.loads((source / 'rtl.command.json').read_text())
    inputs = json.loads((source / 'inputs.json').read_text())
    elf = source / 'input.elf'
    digest = hashlib.sha256(elf.read_bytes()).hexdigest()
    if digest != inputs['binary']['sha256']:
        raise ValueError('archived ELF changed')
    for path, expected in inputs['simv']['image_sha256'].items():
        hasher = hashlib.sha256()
        with Path(path).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(block)
        if hasher.hexdigest() != expected:
            raise ValueError('archived VCS image changed: ' + path)
    output.mkdir(parents=True, exist_ok=False)
    command = []
    for word in original['command']:
        if word.startswith('+COMMIT_WATCHDOG='):
            word = f'+COMMIT_WATCHDOG={args.watchdog}'
        elif word.startswith('+COMMIT_TRACE='):
            word = '+COMMIT_TRACE=' + str(output / 'commit_trace.csv')
        elif word.startswith('+VECTOR_TRACE='):
            word = '+VECTOR_TRACE=' + str(output / 'vector_trace.csv')
        command.append(word)
    command.extend('+' + probe for probe in args.probe)
    (output / 'command.json').write_text(json.dumps(dict(
        command=command, cwd=str(output), source=str(source), elf_sha256=digest,
        scope='diagnostic replay, not a PASS verdict'), indent=2) + '\n')
    with (output / 'console.log').open('w') as log:
        run = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT,
                             timeout=180)
    print(json.dumps(dict(output=str(output), returncode=run.returncode)))


if __name__ == '__main__':
    main()
