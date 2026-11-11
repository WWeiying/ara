#!/usr/bin/env python3
"""Portable source-only delta delivery; never configures, builds, or runs QEMU."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import sys
import tarfile

sys.dont_write_bytecode = True
ROOT = 'qemu-10.2.0'
PRIMARY_SHA = '9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a'
EXCLUDED = 'roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack'
EXCLUDED_TARGET = '/opt/X11/include'
LOCK = 'subprojects/.wraplock'
SCRATCH = 'tests/qemu-iotests/scratch'
SCHEMA = 'stage5-qemu-portable-source-v1'
DTC_SHA = '1fb660c56f7c255b930f9763f58e0b3f3c59d1815fa11bc5cb01d01823540ba4'
DTC_COMMIT = 'b6910bec11614980a21e46fbccc35934b671bd81'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(stream):
    value = hashlib.sha256()
    for data in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(data)
    return value.hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return digest(stream)


def load(path):
    def pairs(items):
        result = {}
        for name, value in items:
            require(name not in result, 'Duplicate JSON field: ' + name)
            result[name] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def safe_name(name):
    require(name and not name.startswith('/') and
            str(PurePosixPath(name)) == name and
            all(part not in ('.', '..') for part in name.split('/')),
            'Noncanonical source path: ' + name)
    return name


def check_links(rows):
    links = {name: row['target'] for name, row in rows.items() if row['kind'] == 'symlink'}
    for name in rows:
        parts = name.split('/')
        require(not any('/'.join(parts[:i]) in links for i in range(1, len(parts))),
                'Member traverses a source symlink: ' + name)
    for name in links:
        pending, seen = name, set()
        while True:
            parts = pending.split('/')
            prefix = next(('/'.join(parts[:i]) for i in range(1, len(parts) + 1)
                           if '/'.join(parts[:i]) in links), None)
            if prefix is None:
                break
            require(prefix not in seen, 'Symlink cycle: ' + name)
            seen.add(prefix)
            target = links[prefix]
            require(not posixpath.isabs(target), 'Absolute symlink: ' + name)
            tail = pending[len(prefix):].lstrip('/')
            pending = posixpath.normpath(posixpath.join(posixpath.dirname(prefix), target, tail))
            require(pending != '..' and not pending.startswith('../'), 'Escaping symlink: ' + name)
            require(pending != EXCLUDED and not pending.startswith(EXCLUDED + '/'),
                    'Symlink reaches excluded member: ' + name)


def archive_inventory(archive, expected_sha):
    require(sha(archive) == expected_sha, 'Primary archive SHA mismatch')
    rows, seen, skipped = {}, set(), []
    members, file_bytes = 0, 0
    with tarfile.open(archive, 'r|xz') as source:
        for member in source:
            members += 1
            name = member.name.rstrip('/') if member.isdir() else member.name
            require(name not in seen, 'Duplicate archive member: ' + name)
            seen.add(name)
            if name == ROOT:
                require(member.isdir(), 'Source root is not a directory')
                continue
            require(name.startswith(ROOT + '/'), 'Archive member outside source root')
            name = safe_name(name[len(ROOT) + 1:])
            if name == EXCLUDED:
                require(member.issym() and member.linkname == EXCLUDED_TARGET,
                        'Known unsafe-link exclusion changed')
                skipped.append(dict(path=name, kind='symlink', target=member.linkname))
                continue
            require(not name.startswith(EXCLUDED + '/'), 'Child of excluded member')
            if member.isfile():
                with source.extractfile(member) as stream:
                    checksum = digest(stream)
                rows[name] = dict(kind='file', sha256=checksum, size=member.size,
                                  executable=bool(member.mode & stat.S_IXUSR))
                file_bytes += member.size
            elif member.isdir():
                rows[name] = dict(kind='directory')
            elif member.issym():
                rows[name] = dict(kind='symlink', target=member.linkname)
            else:
                raise ValueError('Unsupported archive member: ' + name)
    require(skipped == [dict(path=EXCLUDED, kind='symlink', target=EXCLUDED_TARGET)],
            'Expected exact unsafe-link exclusion is missing')
    check_links(rows)
    return rows, dict(members=members, regular_file_bytes=file_bytes, excluded=skipped)


def tree_inventory(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'Expected a real source directory')
    rows, generated = {}, []

    def walk(directory):
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                name = safe_name(path.relative_to(root).as_posix())
                mode = entry.stat(follow_symlinks=False).st_mode
                if name == LOCK:
                    require(stat.S_ISREG(mode) and path.stat().st_size == 0,
                            'Only the exact empty generated wrap lock is allowed')
                    generated.append(dict(path=name, kind='empty_file'))
                    continue
                if name == SCRATCH:
                    require(stat.S_ISDIR(mode) and not any(path.iterdir()),
                            'Only the exact empty generated scratch directory is allowed')
                    generated.append(dict(path=name, kind='empty_directory'))
                    continue
                if stat.S_ISLNK(mode):
                    rows[name] = dict(kind='symlink', target=os.readlink(path))
                elif stat.S_ISDIR(mode):
                    rows[name] = dict(kind='directory')
                    walk(path)
                elif stat.S_ISREG(mode):
                    rows[name] = dict(kind='file', sha256=sha(path), size=path.stat().st_size,
                                      executable=bool(mode & stat.S_IXUSR))
                else:
                    raise ValueError('Unexpected source entry: ' + name)
    walk(root)
    check_links(rows)
    return rows, sorted(generated, key=lambda row: row['path'])


def tree_summary(rows):
    return dict(entries=len(rows), files=sum(r['kind'] == 'file' for r in rows.values()),
                directories=sum(r['kind'] == 'directory' for r in rows.values()),
                symlinks=sum(r['kind'] == 'symlink' for r in rows.values()),
                regular_file_bytes=sum(r.get('size', 0) for r in rows.values()),
                inventory_sha256=hashlib.sha256(canonical(rows)).hexdigest())


def delta(base, final):
    require(not (set(base) - set(final)), 'Unexpected source deletion')
    edits = []
    for name, after in sorted(final.items()):
        before = base.get(name)
        if before != after:
            require(after['kind'] in ('file', 'directory') and
                    (before is None or before['kind'] == after['kind']),
                    'Unexpected source type/link change: ' + name)
            edits.append(dict(path=name, before=before, after=after))
    return edits


def replay(base, edits):
    result, seen = dict(base), set()
    for edit in edits:
        name = safe_name(edit['path'])
        require(name not in seen and result.get(name) == edit['before'], 'Delta preimage mismatch: ' + name)
        after, before = edit['after'], edit['before']
        require(after['kind'] in ('file', 'directory') and
                (before is None or before['kind'] == after['kind']),
                'Unexpected delta type/link change: ' + name)
        seen.add(name)
        result[name] = after
    check_links(result)
    return result


def dtc_identity(archive, final):
    require(sha(archive) == DTC_SHA, 'Fixed DTC archive SHA mismatch')
    tracked, mode_differences = set(), []
    with tarfile.open(archive, 'r:') as original:
        for member in original:
            if member.isdir():
                continue
            name = safe_name(member.name)
            require(member.isfile() and name not in tracked, 'Unexpected DTC archive member')
            tracked.add(name)
            with original.extractfile(member) as stream:
                checksum = digest(stream)
            row = final.get('subprojects/dtc/' + name)
            require(row is not None and row['kind'] == 'file' and row['size'] == member.size and
                    row['sha256'] == checksum, 'DTC source byte mismatch: ' + name)
            executable = bool(member.mode & stat.S_IXUSR)
            if row['executable'] != executable:
                mode_differences.append(dict(path=name, git_archive_executable=executable,
                                             delivery_executable=row['executable']))
    names = {n[len('subprojects/dtc/'):] for n, r in final.items()
             if n.startswith('subprojects/dtc/') and r['kind'] == 'file'}
    require(len(tracked) == 310 and names - tracked == {'.meson-subproject-wrap-hash.txt'},
            'DTC tracked/wrap-marker census differs')
    return dict(commit=DTC_COMMIT, git_archive_sha256=DTC_SHA, tracked_files=310,
                tracked_bytes_identical=True, executable_bit_differences=mode_differences,
                retained_wrap_marker=final['subprojects/dtc/.meson-subproject-wrap-hash.txt'],
                all_component_bytes_in_payload=True, git_archive_needed_for_reconstruction=False)


def capture(archive, source, output, provenance=None, expected_sha=PRIMARY_SHA, dtc_archive=None):
    output = Path(output)
    require(not output.exists(), 'Use a fresh delivery output')
    base, archive_info = archive_inventory(archive, expected_sha)
    final, generated = tree_inventory(source)
    components = dict(dtc=dtc_identity(dtc_archive, final)) if dtc_archive else {}
    edits = delta(base, final)
    require(replay(base, edits) == final, 'Delta does not exactly reproduce final source')
    files = [e for e in edits if e['after']['kind'] == 'file']
    blobs = {e['after']['sha256']: Path(source) / e['path'] for e in files}
    output.mkdir(parents=True)
    payload = output / 'payload.tar.xz'
    with tarfile.open(payload, 'w:xz', format=tarfile.PAX_FORMAT) as bundle:
        for checksum, path in sorted(blobs.items()):
            data = path.read_bytes()
            require(hashlib.sha256(data).hexdigest() == checksum, 'Source changed while capturing')
            member = tarfile.TarInfo('blobs/' + checksum)
            member.size, member.mode = len(data), 0o644
            bundle.addfile(member, io.BytesIO(data))
    manifest = dict(schema=SCHEMA, root=ROOT,
        primary=dict(filename=Path(archive).name, sha256=expected_sha, **archive_info),
        final_tree=tree_summary(final), edits=edits,
        payload=dict(filename=payload.name, sha256=sha(payload), blobs=len(blobs),
                     compressed_bytes=payload.stat().st_size, raw_bytes=sum(p.stat().st_size for p in blobs.values())),
        component_provenance=components,
        generated_policy=[dict(path=LOCK, kind='empty_file'), dict(path=SCRATCH, kind='empty_directory')],
        permission_policy='Preserve owner executable bit; normalize files to 0644/0755; directory ownership/ACL/mtime are not source identity',
        provenance=provenance or {})
    save(output / 'manifest.json', manifest)
    report = dict(state='SOURCE_DELTA_REPLAY_CHECKED_NOT_REBUILT',
        modified_files=sum(e['before'] is not None and e['after']['kind'] == 'file' for e in edits),
        added_files=sum(e['before'] is None and e['after']['kind'] == 'file' for e in edits),
        added_directories=sum(e['before'] is None and e['after']['kind'] == 'directory' for e in edits),
        removed_source_entries=0, observed_generated=generated,
        manifest_sha256=sha(output / 'manifest.json'), payload_sha256=sha(payload),
        payload_bytes=payload.stat().st_size, final_tree=manifest['final_tree'],
        source_edited=False, qemu_built=False, guest_executed=False)
    save(output / 'capture.json', report)
    return report


def payload_bytes(path, manifest):
    require(sha(path) == manifest['payload']['sha256'], 'Payload SHA mismatch')
    required = {e['after']['sha256'] for e in manifest['edits'] if e['after']['kind'] == 'file'}
    result = {}
    with tarfile.open(path, 'r:xz') as bundle:
        for member in bundle:
            require(member.isfile() and re.fullmatch(r'blobs/[0-9a-f]{64}', member.name), 'Unsafe payload member')
            checksum = member.name[6:]
            require(checksum in required and checksum not in result, 'Unexpected/duplicate payload blob')
            data = bundle.extractfile(member).read()
            require(hashlib.sha256(data).hexdigest() == checksum, 'Payload blob SHA mismatch')
            result[checksum] = data
    require(set(result) == required, 'Incomplete payload')
    return result


def reconstruct(archive, bundle, destination):
    bundle, destination = Path(bundle), Path(destination)
    require(not destination.exists(), 'Use a fresh reconstruction destination')
    manifest = load(bundle / 'manifest.json')
    require(manifest['schema'] == SCHEMA and manifest['root'] == ROOT and
            manifest['primary']['sha256'] == PRIMARY_SHA and
            manifest['payload']['filename'] == 'payload.tar.xz', 'Unsupported delivery identity')
    base, archive_info = archive_inventory(archive, PRIMARY_SHA)
    require(archive_info == {k: manifest['primary'][k] for k in archive_info}, 'Archive inventory mismatch')
    final = replay(base, manifest['edits'])
    require(tree_summary(final) == manifest['final_tree'], 'Final inventory mismatch')
    blobs = payload_bytes(bundle / manifest['payload']['filename'], manifest)

    def filtered(member, target):
        if member.name == ROOT + '/' + EXCLUDED:
            require(member.issym() and member.linkname == EXCLUDED_TARGET, 'Unsafe exclusion changed')
            return None
        return tarfile.data_filter(member, target)
    destination.mkdir(parents=True)
    with tarfile.open(archive, 'r:xz') as original:
        original.extractall(destination, filter=filtered)
    root = destination / ROOT
    for edit in manifest['edits']:
        path, after = root / edit['path'], edit['after']
        if after['kind'] == 'directory':
            path.mkdir(parents=True, exist_ok=True)
        else:
            require(after['kind'] == 'file', 'Unexpected delta kind')
            path.parent.mkdir(parents=True, exist_ok=True)
            data = blobs[after['sha256']]
            require(len(data) == after['size'], 'Payload size mismatch')
            path.write_bytes(data)
            path.chmod(0o755 if after['executable'] else 0o644)
    actual, generated = tree_inventory(root)
    require(not generated and actual == final, 'Reconstructed source differs')
    return dict(state='SOURCE_RECONSTRUCTED_NOT_BUILT', final_tree=tree_summary(actual),
                qemu_built=False, guest_executed=False)


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    a = sub.add_parser('capture', allow_abbrev=False)
    a.add_argument('--archive', type=Path, required=True)
    a.add_argument('--source', type=Path, required=True)
    a.add_argument('--output', type=Path, required=True)
    a.add_argument('--origin-receipt', type=Path)
    a.add_argument('--dtc-archive', type=Path)
    a = sub.add_parser('reconstruct', allow_abbrev=False)
    a.add_argument('--archive', type=Path, required=True)
    a.add_argument('--bundle', type=Path, required=True)
    a.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'capture':
        provenance = {}
        if args.origin_receipt:
            receipt = load(args.origin_receipt)
            require(Path(receipt['source']).resolve() == args.source.resolve(), 'Origin source mismatch')
            provenance = dict(origin_receipt_sha256=sha(args.origin_receipt),
                origin_schema=receipt['schema'], configure_arguments=receipt['configure_argv'][1:],
                historical_receipt_is_not_a_reconstruction_dependency=True)
        result = capture(args.archive, args.source, args.output, provenance, dtc_archive=args.dtc_archive)
    else:
        result = reconstruct(args.archive, args.bundle, args.destination)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
