#!/usr/bin/env python3
"""Freeze actual ex_stage branch cones and run bounded VCS, never a SoC build.

Candidate slice is verbatim from ex_stage, not a reimplementation. All omitted
execution units are outside the compared branch cone. Source hashes identify
the snapshot even if its owner continues editing the live dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CORE = 'hardware/deps/cva6/core/'
EX = CORE + 'ex_stage.sv'
BASE = Path('/home/wangwy/dc_runs/ara_main_870cadb9_all_on_20261111_01/'
            'attempt_03/sources/home/wangwy/openproject/ara_dsa_dc_20261110')
FILES = ['hardware/deps/common_cells/src/cf_math_pkg.sv',
         CORE+'include/config_pkg.sv', CORE+'include/cv64a6_imafdcv_sv39_config_pkg.sv',
         CORE+'include/riscv_pkg.sv', CORE+'include/ariane_pkg.sv',
         CORE+'include/build_config_pkg.sv', 'hardware/deps/common_cells/src/lzc.sv',
         CORE+'alu.sv', CORE+'branch_unit.sv']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def slice_source(source, name, candidate):
    start, end = '  // from ALU to branch unit', '  // 3. CSR (sequential)'
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Unknown ex_stage extraction boundary')
    body = source.split(start)[1].split(end)[0]
    if candidate:
        for required in ('assign branch_data = fu_data_i[0];',
                         '.fu_data_i         (branch_data)',
                         '.branch_comp_res_i (branch_comp_res)',
                         'end else begin : gen_direct_branch'):
            if required not in body:
                raise ValueError('Raw single-port wiring contract missing: ' + required)
        comp = 'branch_comp_res'
    else:
        if '.branch_comp_res_i (alu_branch_res)' not in body:
            raise ValueError('Reference is not the old ALU comparator path')
        comp = 'alu_branch_res'
    return '''module ''' + name + ''' import ariane_pkg::*; #(
  parameter config_pkg::cva6_cfg_t CVA6Cfg=config_pkg::cva6_cfg_empty,
  parameter type fu_data_t=logic, branchpredict_sbe_t=logic,
                 bp_resolve_t=logic, exception_t=logic
)(input logic clk_i,rst_ni,v_i,debug_mode_i,
  input fu_data_t [CVA6Cfg.NrIssuePorts-1:0] fu_data_i,
  input logic [CVA6Cfg.NrIssuePorts-1:0] alu_valid_i,branch_valid_i,csr_valid_i,aes_valid_i,
  input logic [CVA6Cfg.NrIssuePorts-1:0][CVA6Cfg.VLEN-1:0] rs1_forwarding_i,rs2_forwarding_i,
  input logic [CVA6Cfg.VLEN-1:0] pc_i,
  input logic is_zcmt_i,is_compressed_instr_i,
  input branchpredict_sbe_t branch_predict_i,
  output bp_resolve_t resolved_branch_o,
  output exception_t flu_exception_o,
  output logic resolve_branch_o,branch_comp_o,
  output logic [CVA6Cfg.VLEN-1:0] branch_result_o
);
''' + body + '\nassign branch_result_o=branch_result;\nassign branch_comp_o=' + comp + ';\nendmodule\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path, default=BASE)
    parser.add_argument('--vcs', default='/home/wangwy/software/synopsys/install/'
                        'vcs/V-2023.12-SP1/bin/vcs')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    src = out/'src'
    src.mkdir()
    origins = {}
    candidate = (ROOT/EX).read_bytes()
    baseline = (args.baseline/EX).read_bytes()
    if digest(baseline) != '8e909ca497423abffa449c8e3213ffa08bd5fa501bd88600985d3f3bcf25bfd3':
        raise ValueError('Unexpected attempt_03 ex_stage reference')
    (src/'ex_stage.candidate.txt').write_bytes(candidate)
    (src/'ex_stage.baseline.txt').write_bytes(baseline)
    origins[str(ROOT/EX)] = digest(candidate)
    origins[str(args.baseline/EX)] = digest(baseline)
    for rel in FILES:
        data = (ROOT/rel).read_bytes()
        if data != (args.baseline/rel).read_bytes():
            raise ValueError('Candidate/reference arithmetic or package drift: '+rel)
        (src/Path(rel).name).write_bytes(data)
        origins[str(ROOT/rel)] = digest(data)
    (src/'cva6_branch_slice.sv').write_text(slice_source(candidate.decode(),'cva6_branch_slice',True))
    (src/'cva6_branch_slice_old.sv').write_text(slice_source(baseline.decode(),'cva6_branch_slice_old',False))
    top = (ROOT/(CORE+'cva6.sv')).read_text()
    definitions = []
    for name in ('fu_data_t','exception_t','branchpredict_sbe_t','bp_resolve_t'):
        found = re.findall(r'(?:localparam|parameter)\s+type\s+'+name+
                           r'\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*,',top)
        if len(found) != 1:
            raise ValueError('Ambiguous actual CVA6 interface: '+name)
        definitions.append('typedef '+found[0]+' '+name+';')
    (src/'branch_types.svh').write_text('\n'.join(definitions)+'\n')
    origins[str(ROOT/(CORE+'cva6.sv'))] = digest(top.encode())
    # JAL retains the decoder's default ADD operation; do not invent a JAL enum.
    decoder = (ROOT/(CORE+'decoder.sv')).read_text()
    jal = decoder.split('riscv::OpcodeJal: begin')[1].split('end')[0]
    if 'instruction_o.op' in jal or 'instruction_o.op                       = ariane_pkg::ADD;' not in decoder:
        raise ValueError('JAL decoder operation contract changed')
    origins[str(ROOT/(CORE+'decoder.sv'))] = digest(decoder.encode())
    shutil.copy2(Path(__file__).with_name('cva6_single_branch_tb.sv'),src/'cva6_single_branch_tb.sv')
    shutil.copy2(__file__,out/'worker.py')
    shutil.copytree(ROOT/'hardware/deps/common_cells/include',out/'include')
    pins = {str(p):digest(p.read_bytes()) for p in out.rglob('*') if p.is_file()}
    save(out/'source-pins.json',pins)
    save(out/'origin-pins.json',origins)
    report = dict(state='FAIL', scope='Verbatim ex_stage branch cone + real ALU/branch_unit; not full ex_stage or SoC',
                  candidate_ex_stage_sha256=digest(candidate), baseline_ex_stage_sha256=digest(baseline),
                  limitations=['RV64 single issue only; no superscalar acceptance',
                               'Finite directed VCS vectors, not exhaustive SAT',
                               'No timing or full-pipeline integration claim'])
    compile_cmd=[args.vcs,'-full64','-sverilog','-timescale=1ns/1ps','+incdir+src',
                 '+incdir+include','-top','cva6_single_branch_tb','-o','simv',
                 *['src/'+Path(p).name for p in FILES],
                 'src/cva6_branch_slice.sv','src/cva6_branch_slice_old.sv',
                 'src/cva6_single_branch_tb.sv']
    commands = [compile_cmd,['./simv','-no_save'],['./simv','-no_save','+NEGATIVE_CONTROL']]
    save(out/'commands.json',commands)
    try:
        for index,cmd in enumerate(commands):
            log=out/('compile.log' if index==0 else 'run.log' if index==1 else 'negative.log')
            with log.open('w') as stream:
                result=subprocess.run(['timeout','--signal=TERM','--kill-after=10s','180',*cmd],
                                      cwd=out,stdout=stream,stderr=subprocess.STDOUT)
            text=log.read_text()
            if index<2 and (result.returncode or re.search(r'(?m)^(Error-|Fatal:)',text)):
                raise RuntimeError('Component failed: '+str(log))
            if index==1:
                rows=re.findall(r'SINGLE_BRANCH_PASS rvc=(\d) checks=(\d+) invalid=(\d+) poison=(\d+)',text)
                if len(rows)!=2 or {r[0] for r in rows}!={'0','1'} or 'SINGLE_BRANCH_MATRIX_PASS' not in text:
                    raise ValueError('Incomplete component checks')
                report['configurations']=[dict(rvc=int(r),checks=int(c),invalid=int(i),poison=int(p)) for r,c,i,p in rows]
            # This VCS installation returns zero even for $fatal; require the
            # actual fatal diagnostic rather than treating rc==0 as a PASS.
            if index==2 and (result.returncode not in (0,1) or 'Fatal:' not in text
                             or 'RAW_COMPARE_MISMATCH' not in text):
                raise ValueError('Comparator negative control did not fail correctly')
        for p,h in pins.items():
            if digest(Path(p).read_bytes()) != h: raise ValueError('Frozen input drift: '+p)
        report.update(state='PASS', negative_control='REJECTED',
                      live_ex_stage_matches_snapshot=digest((ROOT/EX).read_bytes())==digest(candidate))
    except Exception as exc:
        report['error']=str(exc)
        raise
    finally:
        save(out/'report.json',report)
        print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
