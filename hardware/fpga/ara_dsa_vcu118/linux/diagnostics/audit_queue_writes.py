"""Syntax-only overlap inventory; requires pyslang, not an equivalence check."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from pyslang import Bag, SourceManager
from pyslang.parsing import PreprocessorOptions
from pyslang.syntax import SyntaxNode, SyntaxTree


def tokens(node):
    if isinstance(node, list):
        return ''.join(tokens(x) for x in node)
    if not isinstance(node, dict):
        return ''
    if 'text' in node:
        return node['text']
    return ''.join(tokens(v) for k, v in node.items() if k not in ('trivia', 'kind'))


def path_parts(node):
    kind = node.get('kind')
    if kind == 'ScopedName':
        return path_parts(node['left']) + path_parts(node['right'])
    if kind in ('IdentifierName', 'IdentifierSelectName'):
        parts = [('name', tokens(node['identifier']))]
        parts += [('index', tokens(s['selector'])) for s in node.get('selectors', [])]
        return parts
    return []


def scan(path, includes, defines):
    manager = SourceManager()
    pp = PreprocessorOptions()
    pp.additionalIncludePaths = includes
    pp.predefines = defines
    tree = SyntaxTree.fromFile(str(path), manager, Bag([pp]))
    rows = []

    def walk(node, scope='outside_process'):
        kind = str(node.kind).split('.')[-1]
        location = node.sourceRange.start
        if kind in ('AlwaysCombBlock', 'AlwaysFFBlock', 'AlwaysBlock',
                    'AlwaysLatchBlock', 'InitialBlock'):
            scope = f'{kind}:{manager.getLineNumber(location)}:{manager.getColumnNumber(location)}'
        if 'Assignment' in kind and hasattr(node, 'operatorToken') and hasattr(node, 'left'):
            op = str(node.operatorToken).strip()
            if op in ('=', '<=', '|=', '&=', '^=', '+=', '-='):
                lhs = json.loads(node.left.to_json())
                parts = path_parts(lhs)
                if parts and any(k == 'index' for k, _ in parts):
                    rows.append(dict(scope=scope, line=manager.getLineNumber(location),
                                     lhs=tokens(lhs), parts=parts, op=op,
                                     rhs=str(node.right).strip()[:120]))
        for child in node:
            if isinstance(child, SyntaxNode):
                walk(child, scope)
    walk(tree.root)
    groups = defaultdict(list)
    for row in rows:
        groups[(row['scope'], row['parts'][0][1])].append(row)
    findings = []
    for (scope, root), writes in groups.items():
        pairs = []
        shapes = {}
        for write in writes:
            shape = tuple((k, '*' if k == 'index' else v) for k, v in write['parts'])
            shapes.setdefault(shape, write['line'])
        for prefix, whole_line in shapes.items():
            if prefix[-1][0] != 'index':
                continue
            for suffix, partial_line in shapes.items():
                if len(suffix) > len(prefix) and suffix[:len(prefix)] == prefix:
                    pairs.append([whole_line, partial_line])
        if pairs:
            findings.append(dict(scope=scope, root=root, pairs=pairs, writes=writes))
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                diagnostics=[str(d.code) for d in tree.diagnostics], findings=findings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--main-rtl', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.package / 'manifest.json').read_text())
    includes = [str((args.package / x).resolve()) for x in manifest['include_dirs']]
    base = manifest['defines']
    defines = ([k if v is None else f'{k}={v}' for k, v in base.items()]
               if isinstance(base, dict) else list(base))
    defines += ['SYNTHESIS', 'ARA_FPGA_HOST', 'ARA_FPGA_ETHERNET']
    listed = {(args.package / x).resolve() for x in manifest['files']}
    paths = set(args.package.glob('rtl/**/*.sv')) | set(args.package.glob('rtl/**/*.v'))
    if args.main_rtl:
        paths |= set(args.main_rtl.rglob('*.sv'))
    reports = []
    for index, path in enumerate(sorted(paths)):
        if index % 100 == 0:
            print(f'SCAN {index}/{len(paths)} {path}', flush=True)
        report = scan(path.resolve(), includes, defines)
        report['manifest_listed'] = path.resolve() in listed
        reports.append(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as out:
        json.dump(dict(scope='syntax candidates, no elaboration or equivalence proof',
                       defines=defines, files=reports), out, indent=2)
    print(f'FILES {len(reports)}; FINDINGS {sum(len(r["findings"]) for r in reports)}')
    for r in reports:
        for f in r['findings']:
            print(r['path'], f['scope'], f['root'], sorted(set(sum(f['pairs'], []))),
                  'listed='+str(r['manifest_listed']))


if __name__ == '__main__':
    main()
