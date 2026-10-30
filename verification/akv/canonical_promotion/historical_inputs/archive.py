#!/usr/bin/env python3
"""Fixed historical source bindings, not an image acceptance or worker adapter."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CHANGED = {
    'Bender.yml': 'c503ebedf85924cc1add30fcadc7179a9b8fb7b53a03c5ee7139b3b0f3da2e1a',
    'hardware/Makefile': 'be1599812532e4839caeef5ebcf7b901228981d974a78aabdf3fad58e79c274b',
    'hardware/src/vlsu/akv/akv_engine.sv': 'fb7f3f647b734ce639ddf81366b9d5121b25225aad9bcb43e6d97ec5d5ac9bf4',
    'hardware/src/vlsu/qbs/qbs_engine.sv': '70c97021aa34fd0565150e0a39a8da88a87140e4909e9908f0f6e57305da1024',
    'hardware/src/vlsu/vlsu.sv': '39f9b9a76c438fa8fa11762302b3ce2a75df6d223250d041614eefa4546a9443',
}
RECEIPTS = {
    'verification/out/qbacc-soc-20261023-02/build/sim/vcs_source_manifest.json':
        'a6f84fe299eaa54c2f20da76d4b29a5a03fc8c9fcc80e35c51cf8de9bcafe8b3',
    'verification/akv/shared_reader_integration/snapshot-03/manifest.json':
        '035ac16298960fafbe2de94a764af5ad80bf08e0c62fdd0d424369d800b3b72f',
    'verification/out/shared-storage-integration-soc-build-20261025-01/source-pins.json':
        '24e3923862819e2438730011ac3b4ea2dc5cab681dbcc6d0474d9eefe9b4c8fe',
    'verification/out/reader-handoff-build-20261024-01/source-pins.json':
        'dc8d77df586558582ee678a1254b73d30c308f9e3c6ea728bd31aeea69479e15',
    'verification/out/akv-paired-heads-threeway-build-20261023-01/source-pins.json':
        '93946d629d430210f23a397efa85ecbad04b942aaa7cf9558b18e29a561399e1',
    'verification/out/ordinary-rvv-unified-20261025-01/source-pins.json':
        '71c3dc262cf021081000d193ef38984d108f8a7bd9e8a22e711c91bb42a4b34c',
}
BASELINE = next(iter(RECEIPTS))
SCHEMA = 'HISTORICAL_CANONICAL_INPUTS_V1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify_pins(pins):
    for name, sha in pins.items():
        require(digest(name) == sha, 'Pin drift: ' + str(name))


def pins_from_receipt(data):
    if 'schema_version' in data:
        require(data['schema_version'] == 1, 'Unsupported original manifest')
        pins = {row['path']: row['sha256'] for row in data['files']}
        require(len(pins) == len(data['files']), 'Duplicate original source path')
        return pins
    return data['input_pins'] if 'input_pins' in data else data


def files_under(directory):
    require(directory.is_dir() and not directory.is_symlink(), 'Missing/symlink inventory root')
    entries = list(directory.rglob('*'))
    require(not any(p.is_symlink() for p in entries), 'Symlink in archived inventory')
    return {p.relative_to(directory).as_posix(): digest(p) for p in entries if p.is_file()}


def closure(root, receipts, include_files):
    """Derive archive contents from exact receipts, not a caller-supplied map."""
    wanted = dict(CHANGED)
    wanted.update({'hardware/include/' + name: sha for name, sha in include_files.items()})
    baseline = pins_from_receipt(receipts[BASELINE])
    wanted['Bender.lock'] = baseline[str(root / 'Bender.lock')]
    lists = {}
    for name, data in receipts.items():
        pins = pins_from_receipt(data)
        for relative, sha in wanted.items():
            require(pins.get(str(root / relative)) == sha,
                    'Original receipt lacks exact historical input: ' + name + ': ' + relative)
        for absolute, sha in pins.items():
            path = Path(absolute)
            if path.suffix == '.f' or path.name.startswith('bender_script'):
                require(path.is_relative_to(root), 'Unexpected external filelist')
                relative = path.relative_to(root).as_posix()
                require(relative not in lists or lists[relative] == sha, 'Filelist versions differ')
                lists[relative] = sha
    require(receipts[BASELINE]['filelist'] in {str(root / p) for p in lists}, 'Missing original filelist')
    wanted.update(lists)
    wanted.update(RECEIPTS)
    return wanted, lists


def prepare(root, output):
    root = root.resolve(strict=True)
    output = output.resolve()
    require(output.is_relative_to(HERE) and output != HERE, 'Archive must be a fresh owned subdirectory')
    require(not output.exists(), 'Do not overwrite a sealed archive')
    receipts = {}
    for name, sha in RECEIPTS.items():
        require(digest(root / name) == sha, 'Unexpected original receipt: ' + name)
        receipts[name] = read_json(root / name)
    include_files = files_under(root / 'hardware/include')
    baseline = pins_from_receipt(receipts[BASELINE])
    expected_include = {str(Path(name).relative_to(root / 'hardware/include')): sha
                        for name, sha in baseline.items() if Path(name).is_relative_to(root / 'hardware/include')}
    require(include_files == expected_include, 'Current include inventory is not the historical inventory')
    wanted, lists = closure(root, receipts, include_files)
    verify_pins({str(root / name): sha for name, sha in wanted.items()})
    helpers = {p.name: digest(p) for p in HERE.iterdir() if p.suffix in ('.py', '.md')}
    output.mkdir()
    for name in sorted(wanted):
        target = output / 'payload' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / name).read_bytes())
    require(files_under(output / 'payload') == wanted, 'Copied archive differs')
    verify_pins({str(root / name): sha for name, sha in wanted.items()})
    require(files_under(root / 'hardware/include') == include_files, 'Header inventory changed while copying')
    verify_pins({str(HERE / name): sha for name, sha in helpers.items()})
    manifest = dict(schema=SCHEMA, state='ARCHIVED_NOT_PROMOTED', original_root=str(root),
                    changed=CHANGED, receipts=RECEIPTS, include_files=include_files, filelists=lists,
                    payload=wanted, helper_pins=helpers, software_mapping='UNCHANGED_SEPARATE_CONTRACT',
                    compilegraph_include='payload/hardware/include',
                    scope='Source pin consumer only; not whole image/run/UVM acceptance')
    save(output / 'manifest.json', manifest)
    sha = digest(output / 'manifest.json')
    (output / 'manifest.sha256').write_text(sha + '\n')
    Archive(output, sha)
    return sha


class Archive:
    def __init__(self, directory, reviewed_sha256):
        self.directory = Path(directory).resolve(strict=True)
        require(digest(self.directory / 'manifest.json') == reviewed_sha256, 'Archive receipt drift')
        self.report = read_json(self.directory / 'manifest.json')
        r = self.report
        require(r['schema'] == SCHEMA and r['state'] == 'ARCHIVED_NOT_PROMOTED' and
                r['changed'] == CHANGED and r['receipts'] == RECEIPTS, 'Unreviewed archive contract')
        self.root = Path(r['original_root'])
        require(self.root.is_absolute(), 'Original root must be absolute')
        self.payload = self.directory / 'payload'
        actual = files_under(self.payload)
        require(actual == r['payload'], 'Archive inventory/bytes drift')
        for name, sha in RECEIPTS.items():
            require(actual.get(name) == sha, 'Original receipt changed')
        receipts = {name: read_json(self.payload / name) for name in RECEIPTS}
        baseline = pins_from_receipt(receipts[BASELINE])
        require(Path(receipts[BASELINE]['repo_root']) == self.root, 'Original root binding differs')
        include = files_under(self.payload / 'hardware/include')
        expected = {str(Path(name).relative_to(self.root / 'hardware/include')): sha
                    for name, sha in baseline.items() if Path(name).is_relative_to(self.root / 'hardware/include')}
        require(include == expected == r['include_files'], 'Historical include membership differs')
        wanted, lists = closure(self.root, receipts, include)
        require(actual == wanted and lists == r['filelists'], 'Unapproved mapping/payload')

    def pins(self, receipt):
        require(receipt in RECEIPTS, 'Receipt not in the six admitted inputs')
        return pins_from_receipt(read_json(self.payload / receipt))

    def mapped_pins(self, pins):
        """Only five exact historical source identities may change location."""
        mapped = dict(pins)
        for name, sha in CHANGED.items():
            original = str(self.root / name)
            if original in mapped:
                require(mapped.pop(original) == sha, 'Unknown historical version: ' + original)
                target = str(self.payload / name)
                require(target not in mapped or mapped[target] == sha, 'Archive mapping collision')
                require(digest(target) == sha, 'Historical source drift: ' + name)
                mapped[target] = sha
        return mapped

    def verify(self, pins):
        verify_pins(self.mapped_pins(pins))

    def historical_include(self):
        """No scan of live hardware/include; returned paths retain four old .sv packages too."""
        actual = files_under(self.payload / 'hardware/include')
        require(actual == self.report['include_files'], 'Historical header inventory drift')
        return {str(self.payload / 'hardware/include' / name): sha for name, sha in actual.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.source_root, args.output))
