"""Admit one pinned Bender rendering, not arbitrary reordered filelists."""
from collections import Counter
import hashlib
import importlib.util
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / 'template.f'
TEMPLATE_SHA = 'e1670b96487792e24c296c831fbb894e8c14772fdf9f3df819ee3ced79a73644'
spec = importlib.util.spec_from_file_location(
    'graph_v2_original_canonical_builder', HERE.parent / 'canonical_soc/build.py')
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contexts(lines):
    definitions, directories, result = {}, [], []
    for line in lines:
        if line.startswith('+define+'):
            name, _, value = line[8:].partition('=')
            require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name), 'Malformed macro name')
            require(name not in definitions or definitions[name] == value,
                    'Conflicting macro definition')
            definitions[name] = value
        elif line.startswith('+incdir+'):
            for name in line[8:].split('+'):
                path = Path(name)
                require(path.is_absolute() and path.is_dir(), 'Invalid include directory')
                if path not in directories:
                    directories.append(path)
        else:
            require(not line.startswith('+') and Path(line).is_absolute(),
                    'Unsupported filelist directive or relative source')
            result.append((line, dict(definitions), frozenset(directories)))
    return result, directories


def header_inventory(directories):
    names, pins = {}, {}
    for directory in directories:
        for path in sorted(directory.rglob('*')):
            if not path.is_file():
                continue
            name = path.relative_to(directory).as_posix()
            require(name not in names or names[name] == path,
                    'Include search order could change header selection: ' + name)
            names[name] = path
            pins[str(path)] = digest(path)
    return pins


def prove(before, after):
    """Only macro/include ordering and whitespace may differ in this template."""
    old, new = base.tokens(before), base.tokens(after)
    require(Counter(old) == Counter(new), 'Filelist token inventory/count differs')
    left, old_dirs = contexts(old)
    right, new_dirs = contexts(new)
    require(left == right, 'Source order or effective macro/include context differs')
    require(set(old_dirs) == set(new_dirs), 'Global include directory set differs')
    pins = header_inventory(dict.fromkeys([*old_dirs, *new_dirs]))
    # Reject parent-relative includes rather than assuming search-order safety.
    for path in dict.fromkeys([*(Path(row[0]) for row in left), *map(Path, pins)]):
        text = path.read_text()
        for match in re.finditer(r'^\s*`include\s+([^\r\n]+)', text, re.M):
            literal = re.match(r'"([^"]+)"', match[1])
            require(literal is not None, 'Dynamic include needs separate review: ' + str(path))
            require('..' not in Path(literal[1]).parts,
                    'Parent-relative include needs separate review: ' + str(path))
    return dict(sources=len(left), tokens=len(old), include_directories=len(old_dirs),
                source_order_equal=True, macro_context_equal=True,
                include_sets_equal=True, ambiguous_headers=False, header_pins=pins)


def expected_graph(oldtext):
    require(digest(TEMPLATE) == TEMPLATE_SHA, 'Unreviewed Bender template')
    expected = base.expected_graph(oldtext)
    actual = TEMPLATE.read_text()
    prove('\n'.join(expected), actual)
    return base.tokens(actual)


def inputs():
    require(digest(TEMPLATE) == TEMPLATE_SHA, 'Unreviewed Bender template')
    _, directories = contexts(base.tokens(TEMPLATE.read_text()))
    pins = header_inventory(directories)
    paths = [TEMPLATE, *HERE.glob('*.py'), HERE / 'README.md']
    pins.update({str(path): digest(path) for path in paths})
    return pins
