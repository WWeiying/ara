import ast
import copy
from pathlib import Path
import unittest
from completion_cache import CompletionCache, require


def complete(ordinal=0):
    return dict(ordinal=ordinal, returned=True, tuple={'start': 3},
                reads=set(range(1088)), csrs=[3, 0], preloads=2, stores=1,
                entry_step=10, target_pc=123, target_step=20)


TREE = ast.parse(Path(__file__).with_name('audit.py').read_text())


def original_require(fragment, context):
    matches = [n for n in ast.walk(TREE) if isinstance(n, ast.Expr)
               and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
               and n.value.func.id == 'require'
               and any(isinstance(x, ast.Constant) and isinstance(x.value, str)
                       and fragment in x.value for x in ast.walk(n))]
    assert len(matches) == 1
    exec(compile(ast.Module(body=matches, type_ignores=[]), '<actual audit guard>', 'exec'),
         dict(context, require=require))


class CacheTests(unittest.TestCase):
    def test_positive_and_repeated_completion(self):
        gate = CompletionCache(); active = complete()
        gate.finish(None); gate.finish(active)
        frozen = active['reads']
        for _ in range(2112):
            gate.finish(active)
            self.assertIs(active['reads'], frozen)
        self.assertIsInstance(frozen, frozenset)

    def test_missing_read_and_early_write(self):
        for count in (0, 1087):
            active = complete(); active['reads'] = set(range(count))
            with self.assertRaises(ValueError):
                CompletionCache().finish(active)

    def test_duplicate_actual_guard_before_and_after_cache(self):
        for cached in (False, True):
            active = complete()
            if cached:
                CompletionCache().finish(active)
            with self.assertRaises(ValueError):
                original_require('Full oracle mismatch/duplicate',
                                 dict(active=active, i=0, value=91, j=0, expected=91, pc=123))

    def test_actual_returned_status_guard(self):
        for status in (1, 2 << 32, (3 << 32) | 1):
            with self.assertRaises(ValueError):
                original_require('Original returned status',
                                 dict(active=complete(), c={'start': 3}, regs={10: status}))
        original_require('Original returned status',
                         dict(active=complete(), c={'start': 3}, regs={10: 3 << 32}))

    def test_state_changes_after_cache(self):
        changes = [('returned', False), ('preloads', 1), ('stores', 2),
                   ('ordinal', 1), ('csrs', (3, 1)), ('csrs', [3, 0]),
                   ('entry_step', 11), ('target_pc', 124), ('target_step', 21),
                   ('tuple', {'start': 4}), ('reads', frozenset(range(1088))),
                   ('reads', set(range(1088))), ('reads', frozenset(range(1087)))]
        for name, value in changes:
            with self.subTest(name=name, value_type=type(value).__name__):
                gate = CompletionCache(); active = complete(); gate.finish(active)
                active[name] = value
                with self.assertRaises(ValueError):
                    gate.finish(active)

    def test_mutation_is_impossible(self):
        gate = CompletionCache(); active = complete(); gate.finish(active)
        with self.assertRaises(AttributeError):
            active['reads'].add(1088)
        with self.assertRaises(TypeError):
            active['csrs'][0] = 2

    def test_new_call_cannot_inherit_cache(self):
        gate = CompletionCache(); old = complete(); gate.finish(old)
        new = complete(1); new['reads'].remove(1087)
        with self.assertRaises(ValueError):
            gate.finish(new)
        new['reads'].add(1087); gate.finish(new)
        self.assertIs(gate.active, new)


if __name__ == '__main__':
    unittest.main(verbosity=2)
