"""Group7 firmware-only contract; no simulator/build-hardware entry points."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
REV='dbe2b78817ef45b912444afcb85ad6e01a2be135'
DELIVERY='1e48e205df5cec34183222c36d22eb4858466810'
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
BASE=OUT/'operator_soc_20261115_activity_02'
NARROW=('vmul','vmulh','vmulhu','vmulhsu','vmacc','vmadd','vnmsac','vnmsub')
WIDE=('vwmul','vwmulu','vwmulsu','vwmacc','vwmaccu','vwmaccsu')


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1048576),b''): h.update(b)
    return h.hexdigest()


def save(path,obj):
    with Path(path).open('x') as stream:
        json.dump(obj,stream,indent=2,sort_keys=True);stream.write('\n')


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def verify(pins):
    for p,h in pins.items(): require(sha(p)==h,'Input drift: '+p)


def fnv(raw):
    value=14695981039346656037
    for b in raw: value=((value^b)*1099511628211)&((1<<64)-1)
    return value
