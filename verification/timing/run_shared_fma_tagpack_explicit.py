#!/usr/bin/env python3
"""Successor tagpack runner with explicit ADDMUL ownership; old TB stays sealed."""
import argparse
from pathlib import Path
import re
import shutil
import run_operand_ext as api


def explicit_testbench(text):
    anchor = '      .in_ready_o(ir[v]),.flush_i(flush),.result_o(results[v]),.status_o(flags[v]),'
    extra = ("      .exclusive_addmul_i(1'b0),.addmul_result_o(),.addmul_status_o(),.addmul_tag_o(),\n")
    if text.count(anchor) != 1:
        raise ValueError('Legacy new-DUT instance anchor changed')
    adapted = text.replace(anchor, extra + anchor, 1)
    if adapted.replace(extra, '', 1) != text:
        raise ValueError('Adaptation changed more than explicit optional-port bindings')
    return adapted


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--prior-soc', type=Path, required=True)
    a = p.parse_args()
    prior, out = a.prior_soc.resolve(), a.output.resolve()
    if api.read(prior/'report.json')['state'] != 'PASS':
        raise ValueError('Prior SoC missing')
    api.verify(prior)
    out.mkdir(parents=True, exist_ok=False)
    def state(**kw):
        api.save(out/'status.json', kw)
        print(kw, flush=True)
    try:
        state(state='PREPARING')
        source, frozen = prior/'shared/source', out/'source'
        shutil.copytree(source/'hardware/deps', frozen/'hardware/deps', symlinks=True)
        sources = []
        for line in (prior/'shared/sources.f').read_text().splitlines():
            if line.startswith('+incdir+') and any(s in line for s in ('common_cells', 'fpnew', 'fpu_div_sqrt')):
                sources.append(line.replace(str(source), str(frozen)))
            elif line.startswith('/') and any('/deps/'+d+'/' in line for d in
                    ('common_cells', 'fpnew', 'fpu_div_sqrt_mvp')):
                sources.append(line.replace(str(source), str(frozen)))
            elif line.startswith('/') and line.endswith('/tc_clk.sv'):
                sources.append(line.replace(str(source), str(frozen)))
        sources = list(dict.fromkeys(sources))
        (out/'src').mkdir()
        for name in ('simd_fma_shared', 'simd_fpnew'):
            text = (source/f'hardware/src/lane/{name}.sv').read_text()
            for mod in ('simd_fma_shared', 'simd_fpnew'):
                text = re.sub(r'\b'+mod+r'\b', mod+'_prior', text)
            # Some accepted priors already have the ownership port. They need
            # the same explicit idle value as the two current DUT variants.
            prior_has_exclusive = name == 'simd_fpnew' and bool(re.search(
                r'\binput\s+logic\s+exclusive_addmul_i\b', text))
            path = out/'src'/f'{name}_prior.sv'
            path.write_text(text)
            sources.append(str(path))
            path = out/'src'/f'{name}.sv'
            shutil.copy2(api.ROOT/f'hardware/src/lane/{name}.sv', path)
            sources.append(str(path))
        shutil.copy2(api.ROOT/'hardware/src/lane/vmfpu.sv', out/'src/vmfpu_integration.sv')
        old_tb = api.HERE/'shared_fma_tagpack_tb.sv'
        old_sha = api.sha(old_tb)
        text = explicit_testbench(old_tb.read_text())
        if prior_has_exclusive:
            anchor = '    .in_ready_o(ir[2]),.flush_i(flush),.result_o(results[2]),.status_o(flags[2]),'
            if text.count(anchor) != 1:
                raise ValueError('Legacy prior-DUT instance anchor changed')
            text = text.replace(anchor, "    .exclusive_addmul_i(1'b0),\n"+anchor, 1)
        tb = out/'src/shared_fma_tagpack_explicit_tb.sv'
        tb.write_text(text)
        sources.append(str(tb))
        api.save(out/'tb-adaptation.json', dict(original=str(old_tb), original_sha256=old_sha,
            successor=str(tb), successor_sha256=api.sha(tb),
            explicit_exclusive_addmul=0, current_instances=2, prior_has_exclusive=prior_has_exclusive,
            old_testbench_unchanged=True))
        (out/'sources.f').write_text('\n'.join(sources)+'\n')
        shutil.copy2(__file__, out/'worker.py')
        shutil.copy2(Path(api.__file__), out/'run_operand_ext.py')
        pins = {str(f): api.sha(f) for f in out.rglob('*') if f.is_file() and f.name != 'status.json'}
        pins[str(old_tb)] = old_sha
        api.save(out/'source-pins.json', pins)
        state(state='BUILDING')
        cmd = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps', '+define+COMMON_CELLS_ASSERTS_OFF',
               '-top', 'shared_fma_tagpack_tb', '-o', 'simv', '-f', 'sources.f']
        api.save(out/'command.json', dict(compile=cmd))
        api.command(cmd, out, out/'compile.log', None, seconds=600)
        state(state='TESTING')
        log = api.command(['./simv', '-no_save', '+ntb_random_seed=1'], out, out/'run.log', 'TAGPACK_PASS', seconds=600)
        api.verify(out)
        state(state='PASS', result=[s for s in log.splitlines() if s.startswith('TAGPACK_PASS')],
              scope='Original tagpack regression with explicit idle ownership; exclusive Resident tests are separate')
    except Exception as exc:
        state(state='FAIL', reason=str(exc))
        raise


if __name__ == '__main__':
    main()
