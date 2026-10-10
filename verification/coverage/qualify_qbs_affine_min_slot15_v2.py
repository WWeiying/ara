"""Private successor for the exact guard-inclusive slot15 runner configuration."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace

import qualify_qbs_affine_min_slot15 as old
import run_qbs_affine_min_slot15_v2 as run


def collect(source,seal,output):
    deps = {str(path):old.life.digest(path) for path in (
        Path(__file__).resolve(),Path(__file__).with_name('test_run_qbs_affine_min_slot15_v2.py'))}
    original = old.template.closure
    def source_pins(): return old.life.merge_pins(original.source_pins(),deps)
    template_ns = dict(vars(old.template),closure=SimpleNamespace(source_pins=source_pins))
    template = SimpleNamespace(**template_ns)
    template.collect = FunctionType(old.template.collect.__code__,template_ns)
    selected = FunctionType(old.selected_wave.__code__,dict(old.selected_wave.__globals__,run=run))
    reuse = FunctionType(old.slot_reuse.__code__,dict(old.slot_reuse.__globals__,run=run))
    namespace = dict(old.collect.__globals__,run=run,selected_wave=selected,slot_reuse=reuse,template=template)
    FunctionType(old.collect.__code__,namespace)(source,seal,output)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--seal',required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    collect(a.run.resolve(),a.seal,a.output.resolve())
