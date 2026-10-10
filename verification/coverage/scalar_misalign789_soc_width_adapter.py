"""Offline SoC override correction; frozen run/collector and HOLD stay intact."""
import argparse
import ast
import inspect
import json
from pathlib import Path
import re
import shutil
from types import FunctionType, SimpleNamespace

import collect_scalar_misalign789 as original

life, require = original.life, original.require
HOLD = life.OUT / 'scalar-misalign789-qualified-agent-20261008-01'


def derive_override(texts):
    s = {n: original.packed.clean(t) for n, t in texts.items()}
    tbparams, _ = original.packed.unique(r'ara_testharness\s*#\((.*?)\)\s*dut\s*\((.*?)\);', s['tb'])
    require(re.search(r'\.AxiUserWidth\b', tbparams) is None, 'TB unexpected user-width override')
    defaults = []
    for name in ('harness', 'soc'):
        value = int(original.packed.unique(r'parameter\s+int\s+unsigned\s+AxiUserWidth\s*=\s*(\d+)', s[name]))
        defaults.append(value)
    require(defaults == [1, 1], 'Frozen harness/SoC actual user-width defaults')
    hp, _ = original.packed.unique(r'ara_soc\s*#\((.*?)\)\s*i_ara_soc\s*\((.*?)\);', s['harness'])
    require(re.search(r'\.AxiUserWidth\s*\(\s*AxiUserWidth\s*\)', hp) is not None, 'Harness user-width connection')
    function = original.packed.unique(r'function\s+automatic\s+config_pkg::cva6_user_cfg_t\s+gen_usr_cva6_config\s*\([^)]*\)(.*?)endfunction', s['soc'])
    writers = re.findall(r'cfg\.AxiUserWidth\s*=\s*([^;]+);', function)
    require(writers == ['AxiUserWidth'], 'Unique SoC unsigned user-width override')
    for token in (
        'CVA6AraConfig_user = gen_usr_cva6_config(cva6_config_pkg::cva6_cfg);',
        'CVA6AraConfig = build_config_pkg::build_config(CVA6AraConfig_user);'):
        require(token in s['soc'], 'SoC config producer chain')
    require('`ifndef TARGET_GATESIM' in s['soc'], 'Explicit RTL/gatesim source guard')
    rtl_soc, removed = re.subn(r'`else\s+ara_system\s+`endif', '', s['soc'])
    require(removed == 1, 'Exact gatesim alternate instance branch')
    sp, _ = original.packed.unique(r'ara_system\s*#\((.*?)\)\s*i_system\s*\((.*?)\);', rtl_soc)
    require(re.search(r'\.CVA6Cfg\s*\(\s*CVA6AraConfig\s*\)', sp) is not None, 'SoC/system config binding')
    cp, _ = original.packed.unique(r'cva6\s*#\((.*?)\)\s*i_ariane\s*\((.*?)\);', s['system'])
    require(re.search(r'\.CVA6Cfg\s*\(\s*CVA6Cfg\s*\)', cp) is not None, 'System/core config binding')
    require('cfg.DCACHE_USER_WIDTH = CVA6Cfg.AxiUserWidth;' in s['build'], 'Build user-width assignment')
    return 1


def source_proof():
    proof = original.source_proof()
    bookpath = original.shared.oracle.inventory.BUILD / 'build-source-pins.json'
    require(life.digest(bookpath) == original.packed.BOOK_SHA, 'Frozen source book')
    book = json.loads(bookpath.read_bytes())
    paths = dict(tb='hardware/tb/ara_tb.sv', harness='hardware/tb/ara_testharness.sv',
        soc='hardware/src/ara_soc.sv', system='hardware/src/ara_system.sv',
        build='hardware/deps/cva6/core/include/build_config_pkg.sv')
    texts = {}
    for name, relative in paths.items():
        path = life.ROOT / relative
        require(str(path) in book and life.digest(path) == book[str(path)], 'Frozen SoC chain: ' + name)
        proof['pins'][str(path)] = book[str(path)]; texts[name] = path.read_text()
    user_width = derive_override(texts)
    params = dict(proof['parameters'], **{'CVA6Cfg.DCACHE_USER_WIDTH': user_width})
    source = original.packed.clean((life.ROOT / 'hardware/deps/cva6/core/cva6.sv').read_text())
    require(re.search(r'scoreboard_entry_t\s*\[CVA6Cfg\.NrCommitPorts-1:0\]\s*commit_instr_id_commit\s*;',source) is not None,
        'Exact descending packed commit array, port0 is low438 bits')
    body = original.packed.unique(r'localparam\s+type\s+dcache_req_i_t\s*=\s*struct\s+packed\s*\{([^{}]*)\}', source)
    require(body.count('(CVA6Cfg.XLEN/8)-1') == 1, 'Exact byte-enable bound')
    body = body.replace('(CVA6Cfg.XLEN/8)-1', str(params['CVA6Cfg.XLEN']//8-1))
    request = original.packed.packed(body, {}, params)
    require(proof['layouts']['dcache_req_i_t']['width'] == 199 and request['width'] == 136
        and request['fields']['data_wuser'][0] == request['fields']['data_wuser'][1], 'Source-derived only63-bit difference')
    proof['layouts'] = dict(proof['layouts'], dcache_req_i_t=request)
    proof['parameters'] = params
    proof['soc_override_correction'] = dict(base_user_width=64, elaborated_user_width=user_width,
        old_request_width=199, actual_source_request_width=136,
        provenance='TB default -> harness parameter -> SoC gen_usr_cva6_config -> build_config -> cva6 type',
        no_actual_width_inference=True)
    load = original.packed.clean((life.ROOT/'hardware/deps/cva6/core/load_unit.sv').read_text())
    require("assign req_port_o.data_we = 1'b0;" in load
        and re.search(r'\breq_port_o\s*(?:=|<=)', load) is None
        and re.search(r'\breq_port_o\.data_wuser\b', load) is None,
        'Load request user has no producer and write-enable is literal zero')
    proof['unused_load_user'] = dict(field='data_wuser', width=1, writer_count=0,
        required_data_we=0, non_user_fields_must_be_binary=True,
        interpretation='Unread write-user field may be X; no unknown cancellation/address/control bits accepted')
    proof['commit_owner_reader'] = dict(parent_width=876, element_width=438, element=0,
        fields={n:proof['layouts']['scoreboard_entry_t']['fields'][n] for n in ('pc','trans_id')},
        preserved_gates='All original ack/PC/TID/exception/ordered return/handler checks; no unused slot1 interpretation')
    return proof


def read_request(bits, layout):
    require(layout['width'] == 136 and 0 < len(bits) <= 136 and set(bits.lower()) <= set('01xz'),
        'Exact typed request bit string')
    bits = bits.lower().rjust(136, bits[0].lower() if bits[0].lower() in 'xz' else '0')
    result = {}
    require(set(layout['fields']) == {'address_index','address_tag','data_wdata','data_wuser',
        'data_req','data_we','data_be','data_size','data_id','kill_req','tag_valid'}, 'Exact request members')
    for name, (left, right) in layout['fields'].items():
        value = bits[135-left:136-right]
        if name == 'data_wuser':
            require(left == right and len(value) == 1, 'Single unused write-user bit only')
            result[name] = int(value, 2) if value in ('0','1') else None
        else:
            require(set(value) <= {'0','1'}, 'Unknown active request member: '+name)
            result[name] = int(value, 2)
    require(result['data_we'] == 0, 'Source-bound load request cannot write')
    return result


def read_commit_owner(bits, layout, element):
    require(layout['width']==438 and element==0 and 0<len(bits)<=876 and set(bits.lower())<=set('01xz'),
        'Exact typed port0 packed owner')
    bits=bits.lower().rjust(876,bits[0].lower() if bits[0].lower() in 'xz' else '0')
    require(layout['fields']['pc']==[437,374] and layout['fields']['trans_id']==[373,371],
        'Source-derived port0 PC/TID offsets')
    result={}
    for name in ('pc','trans_id'):
        left,right=layout['fields'][name];value=bits[875-left:876-right]
        require(set(value)<={'0','1'},'Unknown active commit owner: '+name)
        result[name]=int(value,2)
    return result


def wave_audit(path, expected, handler_cycles, terminal_cycle):
    # Replace only the packed-request reader, keeping every original owner,
    # sampling, reset, exception, privilege and cancellation predicate intact.
    tree = ast.parse(inspect.getsource(original.wave_audit))
    nodes = [n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='fields']
    require(len(nodes)==1 and len(nodes[0].body)==4, 'Exact original nested field reader')
    guard = ast.parse("""if parent == LSU + '.i_load_unit.req_port_o':
    return read_request(state.get(decl[parent]['code'], 'x'), layouts['dcache_req_i_t'])
""").body[0]
    commit_guard=ast.parse("""if parent == CORE + '.commit_instr_id_commit':
    return read_commit_owner(state.get(decl[parent]['code'], 'x'), layouts['scoreboard_entry_t'], element)
""").body[0]
    nodes[0].body[:0]=[guard,commit_guard]; ast.fix_missing_locations(tree)
    ns=dict(original.wave_audit.__globals__,source_proof=source_proof,read_request=read_request,
        read_commit_owner=read_commit_owner)
    exec(compile(tree,str(Path(__file__).resolve()),'exec'),ns)
    return ns['wave_audit'](path, expected, handler_cycles, terminal_cycle)


def collect(run, seal, out):
    run, out = Path(run).absolute(), Path(out).absolute()
    proof = source_proof()
    failed = json.loads((HOLD / 'failure.json').read_bytes())
    require(failed == dict(status='QUALIFICATION_HOLD_NOT_ADMITTED', reason='Exact source-derived packed probe widths'), 'Exact original HOLD')
    old_scalar = HOLD / 'scalar-comparison.json'; old_vcd = HOLD / 'scalar-misalign.vcd'
    bound = {str(p): life.digest(p) for p in (old_scalar, old_vcd, HOLD / 'failure.json',
        Path(__file__).resolve(), Path(__file__).with_name('test_scalar_misalign789_soc_width_adapter.py'))}
    proof['pins'] = life.merge_pins(proof['pins'], bound)
    real_subprocess = original.subprocess
    def cached_conversion(argv, **kwargs):
        require(argv == [str(original.runner.converter.CONVERTER), '-splitpacked',
            str(run/'scalar-misalign.vpd'), str(out/'scalar-misalign.vcd')]
            and kwargs.get('check') is True and kwargs.get('timeout') == 120, 'Exact original conversion call')
        # Original terminal collector already pinned and converted this exact run.
        require((HOLD/'scalar-comparison.json').read_bytes() == (out/'scalar-comparison.json').read_bytes(), 'Full scalar replay unchanged')
        require(life.digest(old_vcd) == bound[str(old_vcd)], 'Cached VCD unchanged')
        shutil.copyfile(old_vcd, out/'scalar-misalign.vcd')
        kwargs['stdout'].write('Reused exact original HOLD VCD; SHA '+bound[str(old_vcd)]+'\n')
        return real_subprocess.CompletedProcess(argv, 0)
    ns = dict(original.collect.__globals__, wave_audit=wave_audit,
        subprocess=SimpleNamespace(**dict(vars(real_subprocess), run=cached_conversion)))
    FunctionType(original.collect.__code__, ns)(run, seal, out)
    core = out/'qualification.json'; result = json.loads(core.read_bytes())
    require(result['run'] == str(run) and result['run_seal'] == seal, 'Core qualification owner')
    life.check(result['input_pins']); life.check(result['output_pins']); life.check(proof['pins'])
    closure = dict(status='SCALAR_MISALIGN789_SOC_WIDTH_OFFLINE_CLOSURE_NOT_ADMITTED',
        core_qualification=str(core), core_sha256=life.digest(core), source_proof=proof,
        input_pins=proof['pins'], output_pins={str(core):life.digest(core)},
        original_HOLD_preserved=True, VCS_rerun=False, coverage_admitted=False)
    life.save(out/'soc-width-closure.json', closure)
    print(json.dumps(dict(core_sha256=life.digest(core), closure_sha256=life.digest(out/'soc-width-closure.json'))))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--run-seal',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();collect(a.run,a.run_seal,a.output)
