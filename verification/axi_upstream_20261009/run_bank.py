"""Standalone optional #426 bank-response test; no live source edits."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tarfile
from run import ROOT, HERE, BACKUP, COMMON, sha, save


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source', choices=('baseline','current'), required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    common=COMMON+['stream_fifo','stream_mux']
    files=[ROOT/'hardware/deps/common_cells/src'/f'{n}.sv' for n in common]
    rel='hardware/deps/axi/src/axi_to_detailed_mem.sv'
    with tarfile.open(BACKUP) as tar:
        data=tar.extractfile(rel).read() if a.source=='baseline' else (ROOT/rel).read_bytes()
    target=out/'axi_to_detailed_mem.sv'; target.write_bytes(data)
    files += [ROOT/'hardware/deps/axi/src/axi_pkg.sv',target,HERE/'axi_audit_tb.sv',HERE/'bank_error_tb.sv']
    pins={str(f):sha(f) for f in files+[Path(__file__).resolve(),HERE/'run.py']}
    if a.source=='current': pins[str(ROOT/rel)]=sha(ROOT/rel)
    for dep in ('axi','common_cells'):
        for f in (ROOT/'hardware/deps'/dep/'include').rglob('*'):
            if f.is_file(): pins[str(f)]=sha(f)
    save(out/'pins.json',pins)
    cmd=[shutil.which('vcs'),'-full64','-sverilog','-timescale=1ns/1ps',
         '+incdir+'+str(ROOT/'hardware/deps/axi/include'),
         '+incdir+'+str(ROOT/'hardware/deps/common_cells/include'),*map(str,files),
         '-top','bank_error_tb','-o',str(out/'simv'),'-Mdir='+str(out/'csrc')]
    save(out/'compile-command.json',cmd)
    with (out/'compile.log').open('w') as log:
        r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if r.returncode: raise RuntimeError('Compile failed: '+str(out/'compile.log'))
    rows=[]
    for case in range(3):
        f=out/f'case-{case}.log'
        with f.open('w') as log:
            r=subprocess.run([str(out/'simv'),'-no_save',f'+CASE={case}'],cwd=out,
                             stdout=log,stderr=subprocess.STDOUT,timeout=30)
        text=f.read_text()
        rows.append(dict(case=case,status='PASS' if r.returncode==0 and text.count('AUDIT_PASS ')==1
                         and 'Fatal' not in text else 'FAIL',log=str(f),sha256=sha(f)))
        print(rows[-1],flush=True)
    assert all(sha(f)==v for f,v in pins.items()),'Input drift'
    save(out/'summary.json',dict(source=a.source,rows=rows,complete=True))


if __name__=='__main__': main()
