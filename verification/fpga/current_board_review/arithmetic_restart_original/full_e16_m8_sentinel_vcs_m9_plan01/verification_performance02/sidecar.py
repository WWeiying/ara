"""Three local dispatch changes only; immutable original modules are not patched."""
import ast
import inspect
import json
from pathlib import Path
import sys
import textwrap

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'diagnostic01'))
import diagnostic as original


class Strict(original.base.Strict):
    def value(self, address, size):
        if size == 1:
            original.need(address in self.memory, 'Missing actual initialized byte')
            return self.memory[address]
        return super().value(address, size)


class OwnerObserver(original.base.OwnerObserver):
    def rows(self, reader):
        assert reader.fieldnames == original.FIELDS
        for row in reader:
            before = tuple(row.items())
            assert None not in row and all(isinstance(v, str) for v in row.values())
            encoded = json.dumps(before, separators=(',', ':')).encode() + b'\n'
            self.before.update(encoded)
            self.observe(row)
            yield row
            assert tuple(row.items()) == before, 'Sealed checker modified an original row'
            self.after.update(encoded)
            self.count['unmodified_delivered_rows'] += 1


def derive(function, replacements):
    """Exact AST expressions, exactly once each; retain every other statement."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    expected = {ast.dump(ast.parse(old, mode='eval').body):
                ast.parse(new, mode='eval').body for old, new in replacements}
    counts = {key: 0 for key in expected}

    class Replace(ast.NodeTransformer):
        def visit_Call(self, node):
            key = ast.dump(node)
            if key in expected:
                counts[key] += 1
                return ast.copy_location(expected[key], node)
            return self.generic_visit(node)

    derived = Replace().visit(tree)
    assert all(n == 1 for n in counts.values()), 'Original narrow AST sites changed'
    ast.fix_missing_locations(derived)
    namespace = dict(original.__dict__, Strict=Strict, OwnerObserver=OwnerObserver)
    exec(compile(derived, str(HERE / 'derived_original.py'), 'exec'), namespace)
    return namespace[function.__name__]


class Prefix(original.Prefix):
    # Constructors differ only in local subclass selection, never shared globals.
    __init__ = derive(original.Prefix.__init__, [
        ('base.Strict(spec)', 'Strict(spec)'),
        ('base.OwnerObserver(protocol)', 'OwnerObserver(protocol)')])
    consume = derive(original.Prefix.consume, [
        ('self.bins.setdefault(cycle//1000000,Counter())',
         'self.event_bin(cycle//1000000)')])

    def event_bin(self, key):
        if key not in self.bins:
            self.bins[key] = original.Counter()
        return self.bins[key]
