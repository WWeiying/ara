#!/usr/bin/env python3
"""Reuse the frozen native recipe with an explicitly identified pointer variant."""
import json
import argparse
from pathlib import Path
import value_cache_build as build
from value_pointer_sources import generate as pointer_generate


def generate(out):
    return pointer_generate(out)+[Path(__file__)]


if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--output',type=Path,required=True)
    args,_=parser.parse_known_args()
    # Only the source generator changes. The common builder still rebuilds
    # every object, audits real captures, and hashes the imported generators.
    build.generate=generate
    build.main()
    out=args.output.resolve()
    report=json.loads((out/'build.json').read_text())
    try:
        dis=(out/'disassembly.log').read_text()
        # GCC can inline the entire getter into main. Absence of a symbol is
        # not missing execution, and does not prove absence of machine copies.
        generated=(out/'value_cache_execute.h').read_text()
        getter=generated.split('static inline int vptr_value(',1)[1].split('\n}\n',1)[0]
        if 'memcpy' in getter or '*selected=w->cache.values[token]' not in getter:
            raise ValueError('Pointer transport source mismatch')
        if 'vptr_schedule(&plan,visible,w->output[0],AKV_QUANT_MAX_DIM,&w->core.online,vptr_value)' not in generated:
            raise ValueError('Pointer scheduler is not connected')
        report.update(value_pointer=True,
            scope='Qwen3 queries0..7 GQA2 D128 one KV head, original versus direct cached V pointer',
            pointer_transport_source_verified=True,callback_out_of_line='<vptr_value>:' in dis)
    except BaseException as exc:
        report.update(state='VARIANT_AUDIT_FAILED',error=repr(exc))
        raise
    finally:
        (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')
