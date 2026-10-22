#!/usr/bin/env python3
"""Independent-anchor admission correction into prepared03, never old overwrite."""
import argparse
import difflib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def materialize():
    failure=json.loads((HERE/'STOPPED02.json').read_text())
    assert failure['error']=="ValueError('Global RNG changed')"
    assert not (HERE/'host').exists() and not (HERE/'soc').exists() and not (HERE/'spike').exists()
    old=(HERE/'prepare02_generated.py').read_text()
    before="require(source[begin:end]==optimized[begin:optimized.index('        for(unsigned op=',begin)],'Global RNG changed')"
    after="require(source[begin:end]==optimized[optimized.index('    for(unsigned seed='):optimized.index('        for(unsigned op=')],'Global RNG changed')"
    assert old.count(before)==1
    fixed=old.replace(before,after)
    # Keep the extra validation in first-call setup, not inside the original RNG interval.
    start=fixed.index("    anchor='        for(unsigned op=0;op<OPERATION_COUNT;++op)'\n")
    end=fixed.index("    require(source.count('if(checks==482)",start)
    fixed=fixed[:start]+fixed[end:]
    before='''                    for(unsigned i=0;i<64;++i) {
                        ((volatile packed64 *)a)[i]=prefix_inputs[0][i];'''
    after='''                    if(checks==0)
                        for(unsigned i=0;i<64;++i)
                            if(((volatile packed64 *)a)[i]!=prefix_inputs[0][i] ||
                               ((volatile packed64 *)b)[i]!=prefix_inputs[1][i]) {
                                text("MACC_OPT_RNG_FAIL\\n");return 92;
                            }
                    for(unsigned i=0;i<64;++i) {
                        ((volatile packed64 *)a)[i]=prefix_inputs[0][i];'''
    assert fixed.count(before)==1
    fixed=fixed.replace(before,after)
    anchor="    begin=source.index('    for(unsigned seed=');end=source.index('        for(unsigned op=',begin)"
    unique="""    require(all(text.count('    for(unsigned seed=')==1 and text.count('        for(unsigned op=')==1
                for text in (source,optimized)), 'RNG anchors must be unique')
"""
    assert fixed.count(anchor)==1
    fixed=fixed.replace(anchor,unique+anchor)
    fixed=fixed.replace("HERE/'prepared'","HERE/'prepared03'")
    fixed=fixed.replace("HERE/'input_pins02.json'","HERE/'input_pins03.json'")
    fixed=fixed.replace("HERE/'STOPPED02.json'","HERE/'STOPPED03.json'")
    generated=HERE/'prepare03_generated.py'
    with generated.open('x') as stream:stream.write(fixed)
    with (HERE/'independent_anchor.diff').open('x') as stream:
        stream.write(''.join(difflib.unified_diff(old.splitlines(True),fixed.splitlines(True))))


def run():
    from host_transform_test import evaluate
    proof=evaluate()
    assert proof['final_rng_bytes_identical'] and proof['old_absolute_offset_comparison_false']
    import prepare03_generated as producer
    producer.save(HERE/'transform_host_receipt.json',proof)
    producer.main()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('materialize','run'))
    if parser.parse_args().mode=='materialize':materialize()
    else:run()
