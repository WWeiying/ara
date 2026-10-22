#!/usr/bin/env python3
"""Small actual transform replay, without C compilation, models or execution."""
import ast
import hashlib
import json
from pathlib import Path
import unittest


def evaluate():
    import prepare03_generated as producer
    path=Path(producer.__file__)
    tree=ast.parse(path.read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='initialize')
    selected=[];started=False
    for node in function.body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='source':
            started=True
        if started:
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and \
                    isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='write_text':break
            selected.append(node)
    ns=dict(vars(producer))
    exec(compile(ast.Module(body=selected,type_ignores=[]),'actual_transform_only','exec'),ns)
    source,optimized=ns['source'],ns['optimized']
    begin='    for(unsigned seed=';end='        for(unsigned op='
    assert all(s.count(begin)==s.count(end)==1 for s in (source,optimized))
    a,b=source.index(begin),source.index(end)
    x,y=optimized.index(begin),optimized.index(end)
    digest=lambda text:hashlib.sha256(text.encode()).hexdigest()
    return dict(status='PASS_HOST_ACTUAL_FINAL_TRANSFORM_INDEPENDENT_UNIQUE_ANCHORS',
        source_start=a,optimized_start=x,source_length=b-a,optimized_length=y-x,
        old_absolute_offset_comparison_false=source[a:b]!=optimized[a:y],
        final_rng_bytes_identical=source[a:b]==optimized[x:y],
        source_rng_sha256=digest(source[a:b]),optimized_rng_sha256=digest(optimized[x:y]),
        source_model_adjusted=False,C_compiles=0,Spike_runs=0,DUT_runs=0,
        generated_producer_sha256=producer.sha(path))


class TransformTests(unittest.TestCase):
    def test_complete_transform_keeps_rng_bytes(self):
        proof=evaluate()
        self.assertTrue(proof['final_rng_bytes_identical'])
        self.assertTrue(proof['old_absolute_offset_comparison_false'])
        self.assertEqual(proof['source_length'],883)
        self.assertEqual(proof['source_rng_sha256'],proof['optimized_rng_sha256'])


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(TransformTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
