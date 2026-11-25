#!/usr/bin/env python3
"""Static qualification before any C/firmware compile; no new model capture."""
import argparse
import importlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from contract import (HERE,ROOT,OUT,SDK_COMMIT,LLAMA_COMMIT,LLAMA,MODEL,MODEL_SHA,
                      RECEIPTS,PARENT,cases,owned_output,receipt)
from check import require,digest
from build_support import Builder,write_json
from extract import extract


def review(a):
    out=owned_output(a.output); require(not out.exists(),'Fresh review output required')
    inventories=[]
    for path in sorted(OUT.glob('operator_campaign_20261115_*/source-pins.json')):
        pins=json.loads(path.read_text())
        conflicts=[name for name in pins if name.startswith(str(HERE)+'/')]
        require(not conflicts,'Owned helpers already sealed by an active consumer')
        inventories.append(dict(path=str(path),sha256=digest(path),pins=len(pins),
            documentation_pins=[name for name in pins if name.endswith('.md')],owned_conflicts=conflicts))
    out.mkdir(); b=Builder(out)
    sdk,llama=out/'inputs/sdk',out/'inputs/llama'
    b.archive(ROOT,SDK_COMMIT,['software/qbs','apps/common','apps/llama_q4k_repack_bench',
        'apps/llama_q4km_micro','verification/qbs/qbs_ref.c','verification/qbs/qbs_ref.h'],sdk)
    b.archive(a.llama,LLAMA_COMMIT,['ggml/include','ggml/src','gguf-py'],llama)
    require(digest(a.model) == MODEL_SHA,'Not the reviewed actual Qwen3 model')
    b.pin(a.model)
    sys.path.insert(0,str(llama/'gguf-py'))
    gguf=importlib.import_module('gguf')
    model=gguf.GGUFReader(a.model,'r')
    tensors={t.name:t for t in model.tensors}
    data=out/'data'; data.mkdir()
    reports=[]
    for phase,(capture,_) in RECEIPTS.items():
        record=receipt(phase)
        require(record['post_pins_match'] and record['performance_measured'] is False,'Capture receipt state')
        require(digest(capture/'source-pins.json') == record['source_pins_sha256'],'Capture inventory drift')
        if phase == 'decode':
            require(record['state'] == 'REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED' and
                record['activation']['phase'] == 'decode' and record['activation']['position'] == 40 and
                record['activation']['rows'] == 1 and record['activation']['complete_prefill_executed'] and
                record['activation']['input_differs_from_prefill'],'Not actual single-token Decode')
        else:
            require(record['state'] == 'REAL_QWEN3_FFN_CAPTURED_NOT_BENCHMARKED' and
                record['activation']['rows'] == 4 and record['activation']['tokens'] == 40 and
                record['activation']['qkv_boundary_bitwise_unchanged'],'Not reviewed Prefill capture')
        log=capture/'qemu.log'
        require(digest(log) == record['artifacts'][str(log)],'Capture log drift')
        extracted=extract(log.read_text(),phase)
        for path in (capture/'result.json',capture/'source-pins.json',log):
            b.pin(path)
        for item in extracted.values():
            require(item['distinct_rows'] == item['rows'],'Repeated activation rows')
        for c in [c for c in cases() if c['backend'] == 'native' and c['phase'] == phase]:
            weight=next(w for w in record['weights'] if w['tensor'] == c['tensor'])
            tensor=tensors[c['tensor']]
            require(list(map(int,tensor.shape)) == [weight['k'],weight['full_n']] and
                tensor.tensor_type.name == weight['type'],'GGUF native type/full shape mismatch')
            wp=capture/weight['file']; ap=capture/(c['activation_source']+'_f32.bin')
            require(digest(wp) == weight['sha256'] == record['artifacts'][str(wp)] and
                    digest(ap) == record['artifacts'][str(ap)],'Capture artifact drift')
            act=extracted[c['activation_source']]
            require(act['k'] == weight['k'] == c['k'] and act['rows'] == c['m'] and
                    act['raw'] == ap.read_bytes(),'Log/binary/weight complete-K mismatch')
            raw=wp.read_bytes()
            row_bytes=c['k_blocks']*c['weight_block_bytes']
            require(len(raw) == weight['captured_n']*row_bytes and
                    tensor.data.tobytes()[:len(raw)] == raw,'Weights not original native GGUF bytes')
            name=f'{phase}_{c["operator"]}'
            selection=data/name; selection.mkdir()
            (selection/'input_f32.bin').write_bytes(act['raw'])
            # N is an independent output-channel crop; K and quantization blocks are untouched.
            (selection/'weights_row.bin').write_bytes(raw[:c['n']*row_bytes])
            for path in (wp,ap,*selection.iterdir()):
                b.pin(path)
            reports.append(dict(operator=c['operator'],phase=phase,m=c['m'],n=c['n'],k=c['k'],
                native_profile=weight['type'],tensor=c['tensor'],original_shape=[weight['k'],weight['full_n']],
                captured_n=weight['captured_n'],distinct_rows=act['distinct_rows'],position=c['position'],
                classification='native_GGUF_weights_and_actual_'+phase+'_graph_activation',
                requantized=False,source=str(capture),selection=str(selection),log_binary_bit_exact=True,
                gguf_weight_bytes_exact=True,full_k=True))
    require(len(reports) == 4,'Exactly four selected real operator pairs required')
    decode=(data/'decode_ffn_down/input_f32.bin').read_bytes()
    prefill=(data/'prefill_ffn_down/input_f32.bin').read_bytes()
    require(all(decode != prefill[i*len(decode):(i+1)*len(decode)] for i in range(4)),
            'Decode mislabeled Prefill row')
    for name,module in list(sys.modules.items()):
        path=getattr(module,'__file__',None)
        if path and (name == 'gguf' or name.startswith(('gguf.','numpy'))):
            p=Path(path)
            if p.is_file():
                b.pin(p)
    b.pin(ROOT/'AGENTS.md'); b.pin(PARENT/'build.json'); b.pin(PARENT/'source-pins.json')
    for path in sorted(HERE.iterdir()):
        if path.is_file():
            b.pin(path)
    b.pin(out/'commands.json')
    for path in out.glob('*.log'):
        b.pin(path)
    write_json(out/'source-pins.json',b.pins)
    result=dict(state='STATIC_REVIEW_QUALIFIED_NOT_COMPILED',sdk_commit=SDK_COMMIT,llama_commit=LLAMA_COMMIT,
        sdk=str(sdk),llama=str(llama),model=str(a.model),model_sha256=MODEL_SHA,selections=reports,
        cases=cases(),source_pins=str(out/'source-pins.json'),source_pins_sha256=digest(out/'source-pins.json'),
        worker_pin_inventories=inventories,post_pins_match=all(digest(path) == sha for path,sha in b.pins.items()),
        limits=dict(max_pairs=4,no_q4_prefill_k2048_m4_m8=True,simulators=False,production_edits=False),
        gaps=[],scope='Native input provenance only; historical emulator capture is NOT current RTL evidence')
    write_json(out/'review.json',result)
    print(json.dumps(dict(state=result['state'],selections=reports,review=str(out/'review.json')),indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--llama',type=Path,default=LLAMA)
    p.add_argument('--model',type=Path,default=MODEL)
    review(p.parse_args())
