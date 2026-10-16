"""Run exact test ELFs in Linux/QEMU before releasing a board package."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import pexpect

def run(args):
    root=args.root
    manifest=json.loads((root/'manifest.json').read_text())
    initrd=root/'initramfs.cpio'
    with initrd.open('xb') as stream:
        for path in (args.initrd,root/'overlay.cpio'):
            with path.open('rb') as source:shutil.copyfileobj(source,stream)
    all_reports=[]
    for vlen in args.vlen:
        path=root/f'reference_{vlen}.json'
        if path.exists():raise RuntimeError('Reference result already exists')
        command=[str(args.qemu),'-machine','virt','-cpu',
                 f'rv64,v=true,vlen={vlen},elen=64'+''.join(','+x for x in args.cpu_feature),'-smp','1','-m','2G',
                 '-no-reboot','-display','none','-monitor','none','-serial','stdio',
                 '-bios',str(args.bios),'-kernel',str(args.kernel),
                 '-initrd',str(initrd),'-append',
                 'console=ttyS0,115200 earlycon=sbi loglevel=4 rdinit=/init '
                 'unaligned_scalar_speed=unsupported unaligned_vector_speed=unsupported']
        report=dict(scope='QEMU reference, not FPGA result',vlen=vlen,cpu_features=args.cpu_feature,results=[],
                    manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest())
        with (root/f'reference_{vlen}.log').open('x') as log:
            child=pexpect.spawn(command[0],command[1:],encoding='utf-8',timeout=120)
            child.logfile=log
            try:
                child.expect('/ # ')
                for case in manifest['cases']:
                    binary=root/'overlay/opt/ara-tests'/case['name']
                    if hashlib.sha256(binary.read_bytes()).hexdigest()!=case['sha256']:
                        raise RuntimeError('ELF hash changed')
                    child.sendline('/opt/ara-tests/'+case['name']+
                                   '; printf "\\nRVV_EXIT:%s\\n" "$?"')
                    child.expect(r'[\r\n]RVV_EXIT:(\d+)[\r\n]')
                    result=dict(name=case['name'],exit_code=int(child.match[1]),output=child.before)
                    result['passed']=result['exit_code']==0 and case['pass_marker'] in result['output']
                    report['results'].append(result)
                    path.write_text(json.dumps(report,indent=2)+'\n')
                    print(vlen,'PASS' if result['passed'] else 'FAIL',case['name'],flush=True)
                    child.expect('/ # ')
            finally:child.close(force=True)
        report['passed']=len(report['results'])==len(manifest['cases']) and all(x['passed'] for x in report['results'])
        path.write_text(json.dumps(report,indent=2)+'\n');all_reports.append(report)
    if not all(x['passed'] for x in all_reports):return 1
    archive=root/'width_tests.tgz'
    with tarfile.open(archive,'w:gz') as tar:
        for case in manifest['cases']:
            tar.add(root/'overlay/opt/ara-tests'/case['name'],arcname=case['name'])
    manifest.update(reference_passed=True,reference_vlens=args.vlen,reference_cpu_features=args.cpu_feature,
                    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                    archive_bytes=archive.stat().st_size)
    (root/'transfer_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','qemu','bios','kernel','initrd'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--vlen',nargs='+',type=int,default=[512,1024])
    p.add_argument('--cpu-feature',action='append',default=[])
    raise SystemExit(run(p.parse_args()))
