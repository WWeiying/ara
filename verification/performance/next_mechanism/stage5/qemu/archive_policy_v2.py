"""One exact, unused EDK2/Xcode link exclusion; retain tarfile.data_filter."""
import hashlib
import json
import posixpath
import tarfile

ARCHIVE_SHA = '9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a'
ROOT = 'qemu-10.2.0'
SKIP_NAME = ROOT + '/roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack'
SKIP_TARGET = '/opt/X11/include'
EXPECTED_MEMBERS = 84624
EXPECTED_BYTES = 694485712
EXPECTED_LINKS = 73


def exact_exclusion(member):
    return member.name == SKIP_NAME and member.issym() and member.linkname == SKIP_TARGET


def data_filter(member, destination):
    if member.name == SKIP_NAME:
        if not exact_exclusion(member):
            raise ValueError('Known exclusion changed type/target')
        return None
    return tarfile.data_filter(member, destination)


def inside(name):
    return name == ROOT or name.startswith(ROOT + '/')


def inventory(members, destination):
    """Inspect all members before extraction, including link chains in the archive."""
    entries, links, excluded, issues = {}, [], [], []
    rows = []
    for member in members:
        name = member.name
        kind = ('symlink' if member.issym() else 'hardlink' if member.islnk()
                else 'file' if member.isfile() else 'directory' if member.isdir() else 'special')
        row = dict(name=name, kind=kind, size=member.size, target=member.linkname)
        rows.append(row)
        if name in entries:
            issues.append(dict(name=name, reason='duplicate member'))
        entries[name] = row
        if (posixpath.isabs(name) or not inside(name) or
                '..' in name.split('/') or name.rstrip('/') != posixpath.normpath(name)):
            issues.append(dict(name=name, reason='noncanonical/outside member path'))
        if kind in ('symlink', 'hardlink'):
            links.append(row)
        if exact_exclusion(member):
            excluded.append(row)
            continue
        if name == SKIP_NAME or name.startswith(SKIP_NAME + '/'):
            issues.append(dict(name=name, reason='exclusion type/target changed or child present'))
        if kind == 'special':
            issues.append(dict(name=name, reason='special file'))
        try:
            tarfile.data_filter(member, str(destination))
        except tarfile.FilterError as exc:
            issues.append(dict(name=name, reason=type(exc).__name__, detail=str(exc)))

    link_map = {row['name']: row for row in links}

    def resolve(name, trail):
        if not inside(name):
            raise ValueError('link escapes QEMU source root')
        parts = name.split('/')
        for end in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:end])
            if prefix == SKIP_NAME:
                raise ValueError('member/link traverses excluded path')
            link = link_map.get(prefix)
            if not link:
                continue
            if prefix in trail:
                raise ValueError('link cycle')
            target = link['target']
            if posixpath.isabs(target):
                raise ValueError('absolute link')
            if link['kind'] == 'symlink':
                target = posixpath.join(posixpath.dirname(prefix), target)
            target = posixpath.normpath(posixpath.join(target, *parts[end:]))
            return resolve(target, trail | {prefix})
        return name

    for row in rows:
        if row in excluded:
            continue
        try:
            resolved = resolve(row['name'], set())
            if row['kind'] in ('symlink', 'hardlink'):
                row['resolved'] = resolved
        except ValueError as exc:
            issues.append(dict(name=row['name'], reason=str(exc)))

    signature = hashlib.sha256(json.dumps(rows, sort_keys=True,
                                          separators=(',', ':')).encode()).hexdigest()
    return dict(schema='stage5-qemu-archive-inventory-v2',
                members=len(rows), declared_file_bytes=sum(row['size'] for row in rows),
                links=len(links), excluded=excluded, issues=issues, all_links=links,
                member_inventory_sha256=signature)


def require_known(report):
    expected = dict(name=SKIP_NAME, kind='symlink', size=0, target=SKIP_TARGET)
    if (report['issues'] or report['members'] != EXPECTED_MEMBERS or
            report['declared_file_bytes'] != EXPECTED_BYTES or
            report['links'] != EXPECTED_LINKS or report['excluded'] != [expected]):
        raise ValueError('Archive differs from reviewed complete inventory')
