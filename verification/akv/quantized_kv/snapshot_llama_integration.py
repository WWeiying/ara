#!/usr/bin/env python3
"""Archive a reproducible private llama.cpp working state without committing it."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('/home/wangwy/llama/llama.cpp'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(strict=True), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)

    def git(*args):
        return subprocess.check_output(['git', '-C', source, *args])

    head = git('rev-parse', 'HEAD').decode().strip()
    tracked = git('diff', '--binary', '--no-ext-diff', 'HEAD')
    extra = []
    names = ('ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp',
             'ggml/src/ggml-cpu/arch/riscv/quant-kv.h')
    for name in names:
        result = subprocess.run(['git', 'diff', '--binary', '--no-ext-diff', '--no-index',
                                 '/dev/null', name], cwd=source, capture_output=True, check=False)
        if result.returncode != 1 or not result.stdout:
            raise ValueError('Expected new integration source: ' + name)
        extra.append(result.stdout)
    patch = tracked + b''.join(extra)
    if git('rev-parse', 'HEAD').decode().strip() != head or git('diff', '--binary', '--no-ext-diff', 'HEAD') != tracked:
        raise ValueError('External working state changed while exporting')
    (out / 'source.patch').write_bytes(patch)
    changed = git('diff', '--name-only', 'HEAD').decode().splitlines() + list(names)
    manifest = dict(source=str(source), base_commit=head,
        scope='Full observed tracked working diff plus the two new adapter files; includes preexisting private changes, not a claim that all hunks were added in this step',
        patch_sha256=hashlib.sha256(patch).hexdigest(),
        source_sha256={name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in changed})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print('PRIVATE_LLAMA_STATE_ARCHIVED', len(changed), head)


if __name__ == '__main__':
    main()
