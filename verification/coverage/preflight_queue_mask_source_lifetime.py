"""Exact software successor: mask comparison does request old vd; VID did not."""
import argparse
import inspect
from pathlib import Path
import types
import preflight_queue_vid_source_lifetime as prior

APP=prior.ROOT/'apps/riscv-tests/isa/rv64uv/vqueue_mask_source_lifetime.c'
PRIOR_SHA='b8c23b2bc609ba935c5bc55078aedc5c5896f45b3bb5244acb7bec8256782f13'
require=prior.require

def expected(cell,kind):
    if kind!='vid':return prior.expected(cell,kind)
    sew,lmul=prior.CELLS[cell];maximum=(1<<sew)-1
    result=bytearray(prior.expected(cell,'source'))
    for i in range(128*lmul//(sew//8)):
        byte=16+i//8;bit=i%8
        result[byte]=(result[byte]&~(1<<bit)) | ((((maximum-13*i)%(1<<sew))<maximum//2)<<bit)
    return bytes(result)

def namespace():
    require(prior.life.digest(Path(prior.__file__))==PRIOR_SHA,'Frozen VID predecessor drift')
    ns=dict(prior.__dict__,APP=APP,expected=expected,__file__=str(Path(__file__).resolve()))
    source=inspect.getsource(prior.validate)
    old="pair[1].instruction>>26 == 20 and\n                (pair[1].instruction>>15)&31 == 17"
    new="pair[1].instruction>>26 == 26 and\n                (pair[1].instruction>>12)&7 == 4 and (pair[1].instruction>>20)&31 == 24"
    require(source.count(old)==1,'Exact pair predicate changed')
    exec(compile(source.replace(old,new),__file__+':oracle','exec'),ns)
    original=prior.binding
    def binding():
        targets,pins=original()
        snap=prior.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
        pins[str(snap)]='9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'
        pins[str(Path(prior.__file__))]=PRIOR_SHA
        pins[str(Path(prior.__file__).with_name('test_preflight_queue_vid_source_lifetime.py'))]=prior.life.digest(Path(prior.__file__).with_name('test_preflight_queue_vid_source_lifetime.py'))
        prior.life.check(pins);return targets,pins
    ns['binding']=binding
    source=inspect.getsource(prior.build)
    require(source.count("len(rvv)==48")==1 and source.count("test_preflight_queue_vid_source_lifetime.py")==1,'Build adapter identity')
    source=source.replace('len(rvv)==48','len(rvv)==56').replace('test_preflight_queue_vid_source_lifetime.py','test_preflight_queue_mask_source_lifetime.py')
    exec(compile(source,__file__+':build','exec'),ns)
    return ns

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True)
    namespace()['build'](ap.parse_args().output.resolve())
