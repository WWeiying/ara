"""Tcl8.4-compatible successor; sealed01 scope and Python checks unchanged."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import c910_prepare_pack_native as base

HERE=Path(__file__).resolve().parent
ENTRY=HERE/'c910_prepare_pack_native_02.tcl'
TEST=HERE/'test_c910_prepare_pack_native_02.py'
ORIGIN=base.life.OUT/'c910-prepare192-pack48-native-agent-20261007-01'
ORIGIN_SHA='26a1eda95503e501687dd6e1e117bf2980456411b588b71fa52c0f688bc1dd04'
ORIGINAL=HERE/'c910_prepare_pack_native.py'
base.ENTRY=ENTRY
base.__file__=str(Path(__file__).resolve())


def prepare(out):
    origin=base.life.read_bound(ORIGIN/'config.json',ORIGIN_SHA)
    base.life.check(origin['pins'])
    reject=json.loads((ORIGIN/'qualification-reject.json').read_bytes())
    error=(ORIGIN/'error.txt').read_text()
    base.need(reject['status']=='REJECTED_NOT_QUALIFIED' and ' in {' in error and
              'looking for close parenthesis' in error,'Actual01 dialect failure differs')
    text=ENTRY.read_text()
    base.need('{*}' not in text and ' in {' not in text and '[lsearch -exact' in text,
              'Native successor uses unsupported Tcl8.5 syntax')
    regression=subprocess.run([sys.executable,'-B','-m','unittest','test_c910_prepare_pack_native_02','-v'],
        cwd=HERE,text=True,capture_output=True)
    base.need(regression.returncode==0 and regression.stderr.rstrip().endswith('OK'),
              'Successor regression failed: '+regression.stderr)
    extra={str(p):base.life.digest(p) for p in (ORIGINAL,TEST,ORIGIN/'config.json',
        ORIGIN/'error.txt',ORIGIN/'qualification-reject.json',ORIGIN/'terminal.json',
        ORIGIN/'live-identity.json',ORIGIN/'DVEfiles/dve_gui.log')}
    save=base.life.save
    def bound_save(path,data):
        if path==out/'config.json':
            proof=out/'successor-regression.json'
            save(proof,dict(status='ACTUAL02_DISK_ENTRY_AND_TCL84_COMPATIBILITY_TESTS_PASS',
                stdout=regression.stdout,stderr=regression.stderr,returncode=regression.returncode))
            data=dict(data,pins={**data['pins'],**extra,str(proof):base.life.digest(proof)},
                repair='Only Tcl8.4-safe lsearch and eval list expansion; exact240 scope/3740 guard gates unchanged',
                failed01_config_seal=ORIGIN_SHA,failed01_preserved=True)
            base.need(data['instances']==origin['instances'],'Successor target/complement changed')
        save(path,data)
    base.life.save=bound_save
    try:base.prepare(out)
    finally:base.life.save=save


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('prepare','run','verify','stage','el','calibration'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seal')
    ap.add_argument('--stage',choices=base.STAGES);ap.add_argument('--file')
    args=ap.parse_args();out=args.output.absolute()
    if args.mode=='prepare':prepare(out)
    else:
        import os
        seal=args.seal or os.environ.get('C910_PREPARE_PACK_SEAL')
        base.need(seal,'Sealed config required')
        c=base.life.read_bound(out/'config.json',seal);base.life.check(c['pins'])
        if args.mode=='stage':print(json.dumps(base.check_stage(out,c,args.stage)))
        elif args.mode=='el':print(json.dumps(dict(objects=len(base.parse_el((out/args.file).read_text(),c)))))
        elif args.mode=='calibration':
            chosen=[(i['scope'],n['name']) for i in c['instances'] for n in i['targets']
                if (i['index']==0 and n['name'] in ('ex4_frac','ex4_frac_52')) or
                   (i['index']==16 and n['name']=='ex1_oper0_frac')]
            base.need(len(chosen)==3,'Exact calibration identities differ')
            base.parse_el((out/'calibration.el').read_text(),c,chosen)
            base.need((out/'calibration-reset-empty.el').read_bytes()==b'','Calibration reset absent')
            base.life.save(out/'calibration-proof.json',dict(status='ACTUAL_NATIVE_NET_REG_SOURCE_BOUND_CALIBRATION_PASS',
                fields=chosen,pins={str(out/'calibration.el'):base.life.digest(out/'calibration.el')}))
        else:(base.run if args.mode=='run' else base.verify)(out,seal)
