"""Preflight inherited files and aliases before any reconstruction write."""
from collections import Counter, defaultdict
import hashlib
import os
from pathlib import Path
import shutil
import stat


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def relative(name):
    p = Path(name)
    require(not p.is_absolute() and p.parts and '..' not in p.parts and
            p.as_posix() == name and name != '.', 'Noncanonical path: ' + name)
    return p


def parents(root, name):
    p = root / relative(name)
    require(root.is_dir() and not root.is_symlink(), 'Invalid root: ' + str(root))
    for parent in p.parents:
        if parent == root:
            break
        require(not parent.is_symlink() and (not parent.exists() or parent.is_dir()),
                'Non-directory/symlink parent: ' + str(parent))
    return p


def regular(path):
    require(not path.is_symlink() and path.is_file(), 'Not regular: ' + str(path))
    require(path.stat().st_nlink == 1, 'Hardlinked file requires reconciliation: ' + str(path))


def link_state(root, name, target):
    p = parents(root, name)
    require(p.is_symlink() and os.readlink(p) == target, 'Link topology drift: ' + name)
    require(not Path(target).is_absolute(), 'Absolute symlink: ' + name)
    resolved = p.resolve(strict=True)
    require(resolved.is_relative_to(root), 'Symlink escapes root: ' + name)
    require(resolved.is_file() or resolved.is_dir(), 'Special link target: ' + name)
    return dict(path=name, target=target, resolved=str(resolved.relative_to(root)),
                kind='file' if resolved.is_file() else 'directory',
                sha256=sha(resolved) if resolved.is_file() else None)


def plan(source, destination, inherited, archive_links):
    """Return all diagnostics. Only exact, already-correct aliases are admissible."""
    source, destination = Path(source).absolute(), Path(destination).absolute()
    rows, links, issues = [], [], []
    groups = defaultdict(list)
    registry = {}
    for item in archive_links:
        name = str(Path(item['name']).relative_to(destination.name))
        try:
            require(item['kind'] == 'symlink' and name not in registry,
                    'Duplicate/non-symlink archive link: ' + name)
            registry[name] = item['target']
            links.append(link_state(destination, name, item['target']))
        except (ValueError, OSError, RuntimeError) as exc:
            issues.append(dict(path=name, error=str(exc)))
    for name, digest in sorted(inherited.items()):
        row = dict(path=name, expected=digest)
        rows.append(row)
        try:
            src, dst = parents(source, name), parents(destination, name)
            require(src.resolve(strict=True).is_relative_to(source), 'Source escapes root: ' + name)
            require(src.is_file() and sha(src) == digest, 'Source pin mismatch: ' + name)
            if src.is_symlink() or dst.is_symlink():
                require(name in registry and src.is_symlink() and dst.is_symlink(),
                        'Unregistered/asymmetric symlink: ' + name)
                expected = link_state(source, name, registry[name])
                actual = link_state(destination, name, registry[name])
                require(actual == expected and actual['sha256'] == digest,
                        'Alias content conflict; explicit reconciliation required: ' + name)
                row.update(action='KEEP_SYMLINK', actual=digest, resolved=actual['resolved'])
            else:
                regular(src)
                if dst.exists():
                    regular(dst)
                    actual = sha(dst)
                    action = 'KEEP_FILE' if actual == digest else 'COPY_REGULAR'
                else:
                    actual, action = None, 'CREATE_REGULAR'
                row.update(action=action, actual=actual, resolved=name)
            groups[row['resolved']].append(dict(path=name, expected=digest))
        except (ValueError, OSError, RuntimeError) as exc:
            issues.append(dict(path=name, error=str(exc)))
    for target, aliases in groups.items():
        if len({item['expected'] for item in aliases}) != 1:
            issues.append(dict(path=target, error='Conflicting resolved-target pins'))
    changed = [r['path'] for r in rows if r.get('action') in ('COPY_REGULAR', 'CREATE_REGULAR')]
    for name in changed:
        try:
            no_alias_write(name, links)
        except ValueError as exc:
            issues.append(dict(path=name, error=str(exc)))
    return dict(schema='stage5-qemu-reconstruction-plan-v3', source=str(source),
                destination=str(destination), rows=rows, archive_links=archive_links,
                links=links, issues=issues, counts=dict(Counter(r.get('action', 'REJECT') for r in rows)),
                alias_groups={k: v for k, v in groups.items() if len(v) > 1})


def no_alias_write(name, links):
    for link in links:
        target = Path(link['resolved'])
        require(name != link['path'] and Path(name) != target and not (
            link['kind'] == 'directory' and Path(name).is_relative_to(target)),
            'Write affects archive alias; explicit reconciliation required: ' + name)


def clear(report):
    require(not report['issues'], 'Reconstruction preflight rejected: ' + repr(report['issues']))


def future(plan_report, overlay, own_root, own):
    """Check every input copy and overlay against the planned inherited bytes."""
    clear(plan_report)
    source, destination = Path(plan_report['source']), Path(plan_report['destination'])
    rows = {r['path']: r for r in plan_report['rows']}
    issues, edits, copies = [], [], []
    names = list(own)
    require(len(names) == len(set(names)), 'Duplicate owned input names')
    for name in names:
        require(relative(name).name == name, 'Input is not a basename: ' + name)
        regular(Path(own_root) / name)
        require(sha(Path(own_root) / name) == own[name], 'Owned input drift: ' + name)
    destinations = list(overlay.EDITS) + ['target/riscv/trace-events'] + list(overlay.FILES.values())
    require(len(destinations) == len(set(destinations)), 'Duplicate overlay destinations')
    for name in destinations:
        try:
            target = parents(destination, name)
            no_alias_write(name, plan_report['links'])
            require(not target.is_symlink(), 'Overlay destination symlink: ' + name)
            if name in overlay.FILES.values():
                require(not target.exists() and name not in rows, 'New overlay collision: ' + name)
                require(target.parent.is_dir(), 'Missing overlay parent: ' + name)
                src = next(k for k, v in overlay.FILES.items() if v == name)
                require(src in own, 'Unpinned new overlay input: ' + src)
                copies.append(dict(path=name, source=src, sha256=own[src]))
                continue
            if name in overlay.EDITS:
                require(name in rows, 'Unpinned overlay anchor input: ' + name)
            planned = source / name if name in rows else target
            regular(planned)
            text = planned.read_text()
            after = (overlay.transform(name, text) if name in overlay.EDITS
                     else text + overlay.TRACE_EVENTS)
            if name not in overlay.EDITS:
                require('akv_arch_' not in text, 'Trace overlay already present')
            edits.append(dict(path=name, before_sha256=sha(planned),
                              after_sha256=hashlib.sha256(after.encode()).hexdigest()))
        except (ValueError, OSError, RuntimeError) as exc:
            issues.append(dict(path=name, error=str(exc)))
    return dict(schema='stage5-qemu-future-copies-v3', issues=issues, edits=edits,
                new_files=copies, inputs=dict(own))


def verify_links(report):
    root = Path(report['destination'])
    for row in report['links']:
        require(link_state(root, row['path'], row['target']) == row,
                'Preserved alias changed: ' + row['path'])


def apply(report):
    clear(report)
    source, destination = Path(report['source']), Path(report['destination'])
    inherited = {r['path']: r['expected'] for r in report['rows']}
    require(plan(source, destination, inherited, report['archive_links']) == report,
            'Preflight stale before copy')
    for row in report['rows']:
        if row['action'] not in ('COPY_REGULAR', 'CREATE_REGULAR'):
            continue
        src, dst = parents(source, row['path']), parents(destination, row['path'])
        regular(src)
        require(sha(src) == row['expected'], 'Source changed before copy')
        dst.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_NOFOLLOW
        if row['action'] == 'CREATE_REGULAR':
            flags |= os.O_CREAT | os.O_EXCL
        else:
            regular(dst)
            require(sha(dst) == row['actual'], 'Destination changed before copy')
        # Never open a symlink for writing, even if it resolves inside the root.
        with os.fdopen(os.open(dst, flags, 0o666), 'wb') as output:
            require(stat.S_ISREG(os.fstat(output.fileno()).st_mode), 'Nonregular output')
            output.truncate(0)
            with src.open('rb') as input_file:
                shutil.copyfileobj(input_file, output)
        require(sha(dst) == row['expected'], 'Copy verification failed: ' + row['path'])
    for row in report['rows']:
        require(sha(destination / row['path']) == row['expected'], 'Inherited post-copy drift')
    verify_links(report)
