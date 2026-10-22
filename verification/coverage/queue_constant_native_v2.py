"""Exact single-bit DVE display normalization; frozen01 and its helpers remain unchanged."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import queue_constant_native as old

SOURCE=Path(old.__file__).resolve()
SOURCE_SHA='1686e5f9cb896530648eefd3aca8b0f4a273b4f24c89337dd36ed2e1d8bbb8c1'

def namespace():
    old.require(old.life.digest(SOURCE)==SOURCE_SHA,'Frozen predecessor source drift')
    text=SOURCE.read_text()
    changes={
        "native_label=name if scalar else name+'['+str(left)+':'+str(right)+']'":
        "native_label=name if scalar or left==right==0 else name+'['+str(left)+':'+str(right)+']'",
        "require(signature.endswith(declaration),'Native declaration signature differs')":
        "require(signature.endswith(declaration) or (s['left']==s['right']==0 and signature.endswith(name)), 'Native declaration signature differs')"
    }
    for before,after in changes.items():
        old.require(text.count(before)==1,'Exact normalization anchor drift');text=text.replace(before,after)
    ns=dict(__name__='queue_constant_exact_single_bit_successor',__file__=str(Path(__file__).resolve()))
    exec(compile(text,str(SOURCE),'exec'),ns)
    return ns

def prepare(out):
    ns=namespace()
    def save(path,value):
        if path==out/'config.json':
            value['pins']=old.life.merge_pins(value['pins'],{str(SOURCE):SOURCE_SHA,
                str(Path(__file__).resolve()):old.life.digest(Path(__file__)),
                str(Path(__file__).with_name('test_queue_constant_native_v2.py')):
                    old.life.digest(Path(__file__).with_name('test_queue_constant_native_v2.py'))})
            value['display_adapter']='ONLY_VECTOR_LEFT_RIGHT_0_COLLAPSES_TO_SCALAR_NATIVE_DISPLAY'
            value['predecessor_source_sha256']=SOURCE_SHA
            old.life.check(value['pins'])
        old.life.save(path,value)
    proxy=SimpleNamespace(**vars(old.life));proxy.save=save
    ns['life']=proxy
    ns['prepare'](out)
    c=json.loads((out/'config.json').read_bytes())
    print(json.dumps(dict(final_config_seal=old.life.digest(out/'config.json'),
        bit_directions=len(old.bitset(c)),EDA_started=False)))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=('prepare','run','verify','el'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seal');ap.add_argument('--file')
    a=ap.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode=='el':
        ns=namespace();c=json.loads((out/'config.json').read_bytes())
        print(json.dumps(dict(bit_directions=len(ns['parse_el']((out/a.file).read_text(),c)))))
    else:namespace()[a.mode](out,a.seal)
