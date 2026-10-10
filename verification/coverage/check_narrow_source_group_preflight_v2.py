"""Finish software preflight on the existing ELF; no rebuild, RTL or VCS."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import build_narrow_source_group_preflight as prior

life,require,OUT=prior.life,prior.require,prior.OUT
FAILED=OUT/'narrow-source-group-preflight-735-agent-20261006-01'
PRIOR_SHA='a80525476bc284e0dcb6ac4fe0af8db20e44072a3ac6f50aad403bee3fbaae99'
FAILED_PINS={str(FAILED/name):sha for name,sha in (
    ('input.elf','b483f1616d5abdc1ff6ed8f32ad56160802abcc5ca3eac06764b1918ba456913'),
    ('target-receipt.json','d8982294a13b2eca8a7cb50882831e29c7e41f9b0ca7a2eddf4e46ed67c26d98'),
    ('compile-command.json','afbde9c62edc7fd58c573f9341fd624edf24e1ee72dbf095324014d015c0b1bb'),
    ('failure.json','d5b86e93b4d49aaf5b5ea399374c428bb4ba0b042ab854b7a36b223aa42da1bb'))}


def rvv_words(disassembly):
    result=[]
    for line in disassembly.splitlines():
        m=re.match(r'\s*([0-9a-f]+):\s+(.*?)\t',line)
        if not m:continue
        field=m[2].strip()
        if re.fullmatch(r'[0-9a-f]{8}',field):word=int(field,16)
        elif re.fullmatch(r'(?:[0-9a-f]{2}\s+){3}[0-9a-f]{2}',field):
            word=int.from_bytes(bytes.fromhex(field),'little')
        else:continue
        if word&127==0x57 or word&127 in (7,39) and word>>12&7 in (0,5,6,7):
            result.append((int(m[1],16),word))
    return result


def verify_words(words,symbols):
    expected=[0x0022f057,0x02050a07,0x02058c07,0x02058c27,0xc0247057,prior.FAULT,
              0x0022f057,0x02050c27,0xc0247057,0x0341bc57,0x0022f057,0x02058c27]
    require([w for _,w in words]==expected and len({pc for pc,_ in words})==12 and
            (symbols['ng_fault'],prior.FAULT) in words and (symbols['ng_recovery'],0x0341bc57) in words,
            'Exact12 explicit opcode sequence/PC required; no implicit vector')


def prepare(out):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh software-only output required')
    require(life.digest(Path(prior.__file__))==PRIOR_SHA,'Frozen predecessor drift')
    life.check(FAILED_PINS)
    receipt=life.read_bound(FAILED/'target-receipt.json',FAILED_PINS[str(FAILED/'target-receipt.json')])
    life.check(receipt['pins'])
    require(receipt['baseline']==735 and receipt['baseline_seal']==prior.BASE_SEAL and
            receipt['rejected_opcode']==prior.FAULT and len(receipt['targets'])==2 and
            all(t['before735'] is False for t in receipt['targets']),'Static sealed binding differs')
    require(json.loads((FAILED/'failure.json').read_bytes())['reason']==
            'Exact12 explicit RVV opcodes required; implicit lowering forbidden','Only known parser rejection recoverable')
    require(not (FAILED/'spike.trace').exists(),'Unexpected previous Spike execution')
    pins=life.merge_pins(receipt['pins'],{str(x):life.digest(x) for x in FAILED.iterdir() if x.is_file()})
    pins=life.merge_pins(pins,FAILED_PINS)
    objdump=prior.LLVM/'llvm-objdump'
    for path in (objdump,Path(__file__).resolve(),Path(__file__).with_name('test_narrow_source_group_preflight_v2.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    elf=FAILED/'input.elf'
    symbols={n:prior.shared._elf_symbol(elf,prior.LLVM/'llvm-readelf',n) for n in prior.SYMBOLS}
    words=rvv_words(subprocess.check_output([str(objdump),'-d',str(elf)],text=True,timeout=30))
    verify_words(words,symbols)
    command=[str(prior.SPIKE),'--isa=rv64gcv_zvl1024b','--priv=msu','--pmpregions=0',
             '-m0x80000000:0x200000','-l','--log-commits',str(elf)]
    life.check(pins);out.mkdir()
    life.save(out/'spike-command.json',command)
    try:
        with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as trace:
            subprocess.run(command,check=True,timeout=180,stdout=stdout,stderr=trace)
        validation=prior.validate(prior.shared.parse_spike_commits(out/'spike.trace'),symbols,
                                  (out/'spike.trace').read_text())
        life.save(out/'validation.json',validation);life.check(pins)
        pins=life.merge_pins(pins,{str(x):life.digest(x) for x in out.iterdir() if x.is_file()})
        life.save(out/'preflight-manifest.json',dict(status='SAME_ELF_SOFTWARE_PREFLIGHT_PASS_NOT_DUT_NOT_ADMITTED',
            input_elf=str(elf),elf_sha256=life.digest(elf),baseline=735,baseline_seal=prior.BASE_SEAL,
            targets=receipt['targets'],pins=pins,symbols=symbols,explicit_RVV=words,validation=validation,
            rebuild_performed=False,VCS_started=False,coverage_admitted=False))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight-manifest.json'),validation=validation)))
    except Exception as error:
        life.save(out/'failure.json',dict(status='SOFTWARE_PREFLIGHT_FAILURE_NOT_DUT',reason=str(error)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.absolute())
