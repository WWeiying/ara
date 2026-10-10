"""Explicit width/configuration derivation supplement to immutable padding proof01."""
import argparse
import copy
import json
from pathlib import Path
import re
import prove_vlsu_address_padding770 as old

PRIOR = old.OUT / 'vlsu-address-padding51-static770-agent-20261007-01.json'
PRIOR_SHA = '74ff351fbe364df946a8d8260946377fad0f57f47bc7e46c869d87721daa4150'
EXTRA = {
    'hardware/tb/ara_testharness.sv': '2170512673680e73b91cce44a0a600bb32000427404b9026238b2914af20482c',
    'hardware/src/ara_system.sv': '3b571d5ba67cbc38040d10656250d492d127c900f3981eae667c8902432b2581',
}
require = old.require


def clean(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)


def one(pattern, text, message):
    matches = re.findall(pattern, text, re.S)
    require(len(matches) == 1, message)
    return matches[0]


def binding(text, instance):
    matches = list(re.finditer(r'\)\s*' + re.escape(instance) + r'\s*\(', text))
    require(len(matches) == 1, 'Unique instantiated owner: ' + instance)
    end = matches[0].start(); depth = 1; pos = end - 1
    while pos >= 0 and depth:
        if text[pos] == ')': depth += 1
        elif text[pos] == '(': depth -= 1
        pos -= 1
    require(depth == 0 and re.search(r'\b\w+\s*#\s*$', text[:pos+1]), 'Parameterized instance boundary')
    params = re.findall(r'\.([A-Za-z_]\w*)\s*\(\s*([^()]*)\s*\)', text[pos+2:end])
    require(len(params) == len({k for k,v in params}), 'Duplicate instance parameter')
    return {k:v.strip() for k,v in params}


def system_binding(text):
    branch = one(r'`ifndef\s+TARGET_GATESIM\s+(ara_system\s*#\(.*?)\s*`else\s+ara_system\s*`endif\s+i_system\s*\(',
                 text, 'Explicit RTL/gatesim system branch')
    return binding(branch + ' i_system (', 'i_system')


def semantic_contract(texts):
    """Restricted source recognizer, deliberately independent of source hash rejection."""
    t = {rel:clean(value) for rel,value in texts.items()}
    def get(name):
        return t[next(rel for rel in t if Path(rel).name == name)]
    largest = one(r'typedef\s+logic\s*(signed\s+|unsigned\s+)?\[\s*(\d+)\s*:\s*0\s*\]\s+largest_addr_t\s*;',
                  get('axi_pkg.sv'), 'Unsigned largest_addr_t declaration')
    require(largest[0].strip() != 'signed', 'Signed128 destination')
    width = int(largest[1]) + 1; require(width == 128, 'Actual largest_addr_t not128')
    pkg = get('ara_pkg.sv')
    for field in ('addr','vaddr'):
        require(re.search(r'axi_pkg::largest_addr_t\s+'+field+r'\s*;',
                          one(r'typedef\s+struct\s+packed\s*\{([^{}]+)\}\s*addrgen_axi_req_t\s*;', pkg, 'Request typedef')), 'Wrong record address type')
    tb_width = int(one(r'localparam\s+AxiAddrWidth\s*=\s*(\d+)\s*;', get('ara_tb.sv'), 'Actual TB AXI width'))
    require(tb_width == 64, 'TB width not64')
    chain = [('ara_tb.sv','dut','AxiAddrWidth'), ('ara_testharness.sv','i_ara_soc','AxiAddrWidth'),
             ('ara_soc.sv','i_system','AxiAddrWidth'), ('ara_system.sv','i_ara','AxiAddrWidth'),
             ('ara.sv','i_vlsu','AxiAddrWidth'), ('vlsu.sv','i_addrgen','AxiAddrWidth')]
    rows = []
    for source, instance, param in chain:
        params = system_binding(get(source)) if instance == 'i_system' else binding(get(source), instance)
        require(params.get(param) == 'AxiAddrWidth', 'AXI width override at '+instance)
        rows.append(dict(source=source, instance=instance, parameter=param, expression=params[param]))
    soc = get('ara_soc.sv')
    user = one(r'function\s+automatic\s+config_pkg::cva6_user_cfg_t\s+gen_usr_cva6_config\(.*?endfunction', soc, 'Configuration override function')
    require(not re.search(r'cfg\.(?:XLEN|PLEN)\s*=', user), 'XLEN/PLEN override')
    require(re.search(r'CVA6AraConfig_user\s*=\s*gen_usr_cva6_config\(cva6_config_pkg::cva6_cfg\)', soc) and
            re.search(r'CVA6AraConfig\s*=\s*build_config_pkg::build_config\(CVA6AraConfig_user\)', soc), 'Actual built configuration owner')
    conf = get('cv64a6_imafdcv_sv39_config_pkg.sv')
    require(re.search(r'package\s+cva6_config_pkg\s*;', conf), 'Selected config package')
    xlen = int(one(r'localparam\s+CVA6ConfigXlen\s*=\s*(\d+)\s*;', conf, 'Actual XLEN'))
    require(xlen == 64 and re.search(r"XLEN\s*:\s*unsigned'\(CVA6ConfigXlen\)", conf), 'Config XLEN binding')
    build = get('build_config_pkg.sv')
    plen_expr = one(r'cfg\.PLEN\s*=\s*([^;]+);', build, 'Unique PLEN assignment')
    match = re.fullmatch(r'\s*\(CVA6Cfg.XLEN\s*==\s*(\d+)\)\s*\?\s*(\d+)\s*:\s*(\d+)\s*', plen_expr)
    require(match is not None, 'Unknown PLEN computation')
    selector, yes, no = map(int, match.groups()); plen = yes if xlen == selector else no
    require(plen == 56 and re.search(r'cfg\.XLEN\s*=\s*CVA6Cfg.XLEN\s*;', build), 'Actual PLEN not56')
    for source, instance, expected in [('ara_soc.sv','i_system','CVA6AraConfig'),
                                      ('ara_system.sv','i_ara','CVA6Cfg'),
                                      ('ara.sv','i_vlsu','CVA6Cfg'), ('vlsu.sv','i_addrgen','CVA6Cfg')]:
        params = system_binding(get(source)) if instance == 'i_system' else binding(get(source),instance)
        require(params.get('CVA6Cfg') == expected, 'CVA6 configuration not forwarded')
    addrgen = get('addrgen.sv')
    require(re.search(r'axi_addr_t\s*=\s*logic\s*\[AxiAddrWidth-1:0\]', addrgen), 'Signed/widened axi_addr_t')
    for name in ('paddr','idx_final_paddr'):
        decls = re.findall(r'logic\s*\[CVA6Cfg.PLEN-1:0\]\s+'+name+r'\s*;', addrgen)
        require(decls and len(decls) == len(re.findall(r'\b'+name+r'\s*;', addrgen)), 'Physical temporary declaration changed')
    require(re.search(r'axi_addr_t\s+idx_final_vaddr_d\s*,\s*idx_final_vaddr_q\s*;', addrgen), 'Indexed destination width')
    queue_writes = re.findall(r'\baxi_addrgen_queue(?:\.\w+)?\s*=', addrgen)
    require(len(queue_writes) == 6 and all(w.strip().startswith('axi_addrgen_queue ') for w in queue_writes), 'Extra field producer')
    blocks = re.findall(r"axi_addrgen_queue\s*=\s*'\{(.*?)\};", addrgen, re.S)
    values = [dict((k,v.strip()) for k,v in re.findall(r'\b(addr|vaddr)\s*:\s*([^,\n]+)', b)) for b in blocks]
    require(values == [dict(addr="'0",vaddr="'0"), dict(addr='paddr',vaddr='axi_addrgen_q.addr'),
                       dict(addr='paddr',vaddr='axi_addrgen_q.addr'), dict(addr='idx_final_paddr',vaddr='idx_final_vaddr_q'),
                       dict(addr='paddr',vaddr="'0")], 'New arithmetic/signed/widened producer')
    fifo = get('fifo_v3.sv')
    require(re.findall(r'\bmem_n(?:\[[^]]+\])?\s*=\s*([^;]+);', fifo) == ['mem_q','data_i'], 'FIFO next-state extra producer')
    require(re.findall(r'\bmem_q\s*<=\s*([^;]+);', fifo) == ["{FifoDepth{dtype'('0)}}",'mem_n'], 'FIFO reset/update changed')
    require(re.search(r'else\s+if\s*\(!gate_clock\)\s*begin\s*mem_q\s*<=\s*mem_n;', fifo), 'FIFO gated update')
    vstu = get('vstu.sv')
    require(re.findall(r'\bb_meta_in\.vaddr\s*=\s*([^;]+);', vstu) == ['axi_addrgen_req_i.vaddr'], 'Metadata extra address producer')
    require(re.search(r"b_meta_in\s*=\s*'0\s*;",vstu), 'Metadata default reset changed')
    return dict(largest_addr_t=dict(width=width,unsigned=True), AxiAddrWidth=dict(value=tb_width,instance_chain=rows),
                CVA6Cfg=dict(selected_package='cv64a6_imafdcv_sv39_config_pkg.sv',XLEN=xlen,PLEN=plen,
                             PLEN_expression=plen_expr.strip(),owner='CVA6AraConfig',forwarded_to='i_addrgen'),
                source_widths=dict(paddr=plen,idx_final_paddr=plen,axi_addrgen_q_addr=tb_width,idx_final_vaddr_q=tb_width),
                unsigned_extension='Unsigned packed RHS56/64 extended to unsigned128; arithmetic narrowed before metadata assignment',
                writer_count=6, metadata_address_writer_count=1,
                testing_scope='Restricted semantic recognizer negative tests independent of hashes; exact hashes additionally close unsupported source forms')


def prepared_self_candidate(path, candidates, derived):
    """Exclude only proven *unexecuted requests* from historical-application inventory."""
    import vlsu_address_padding_native770 as native
    config_path = path.parent / 'config.json'
    require(path.name == 'candidate.el' and config_path.is_file(), 'Unproven overlapping EL')
    c = json.loads(config_path.read_bytes())
    require(c['schema'] == 'VLSU_PADDING51_NATIVE770_PREPARED_V1' and c['baseline'] == 770 and
            c['output'] == str(path.parent) and c['launch_authorized'] is False and
            c['population_application'] is False and not (path.parent/'execution.json').exists() and
            not (path.parent/'capture-result.json').exists(), 'Not an unexecuted self candidate')
    require(c['pins'].get(str(path)) == old.digest(path), 'Unsealed prepared EL')
    own = Path(native.__file__).resolve()
    require(c['pins'].get(str(own)) == old.digest(own), 'Other candidate generator')
    proofs = [Path(p) for p,sha in c['pins'].items() if sha == c['proof_seal'] and p.endswith('.json')]
    require(len(proofs) == 1 and old.digest(proofs[0]) == c['proof_seal'], 'Missing producer proof pin')
    p = json.loads(proofs[0].read_bytes())
    require(p['schema'] == 'VLSU_ADDRESS_PADDING770_SOURCE_PROOF_V1' and p['baseline'] == 770 and
            p['candidates'] == candidates and p['directions'] == 6528, 'Different source-derived target set')
    require(c['proof_seal'] == PRIOR_SHA or p.get('explicit_semantic_derivation') == derived,
            'Other source derivation')
    expected = {(x['scope'],x['name'],bit,d) for x in candidates for bit in range(64,128) for d in ('0to1','1to0')}
    require(set(native.parse_el(path.read_text(),c)) == expected, 'Not exact prepared51 request')
    for instance in c['instances']:
        require(instance['retained_target_bits'] == {s['name']:list(range(64)) for s in instance['signals']},
                'Prepared candidate lost low64 protection')
    return old.digest(config_path)


def evidence():
    require(old.digest(PRIOR) == PRIOR_SHA, 'Proof01 drift')
    prior = json.loads(PRIOR.read_bytes()); pins = dict(prior['pins'])
    for path,sha in pins.items(): require(old.digest(path) == sha, 'Frozen dependency drift')
    book = json.loads((old.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
    selected = [p for p in book if re.search(r'/cv\w+_config_pkg\.sv$', p)]
    require(selected == [str(old.ROOT/'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv')], 'Ambiguous frozen configuration package')
    texts = {rel:(old.ROOT/rel).read_text() for rel in old.SOURCES}
    for rel,sha in EXTRA.items():
        p=old.ROOT/rel
        require(book.get(str(p)) == sha and old.digest(p) == sha, 'Missing actual hierarchy source')
        texts[rel]=p.read_text(); pins[str(p)]=sha
    derived=semantic_contract(texts); old.source_contract({r:texts[r] for r in old.SOURCES})
    for row in prior['old_EL_inventory']:
        require(old.digest(row['path']) == row['sha256'], 'Old EL drift')
        old.duplicates(Path(row['path']).read_text(),old.names())
    # Closed historical inventory is immutable. New unrelated ELs are checked,
    # but self-generated unexecuted requests are classified by sealed provenance.
    historic = {row['path'] for row in prior['old_EL_inventory']}
    for path in sorted(set(old.OUT.rglob('*.el')) | set((old.ROOT/'verification/coverage/waivers').rglob('*.el'))):
        if str(path) in historic: continue
        try:
            old.duplicates(path.read_text(),old.names())
        except ValueError:
            prepared_self_candidate(path,prior['candidates'],derived)
    import inventory_operand_debug
    ledger=(old.BASE/'combined-inputs.txt').read_text().splitlines()
    design=inventory_operand_debug.Design(Path(ledger[0]))
    for scope,expected in [('ara_tb.dut','ara_testharness'),('ara_tb.dut.i_ara_soc','ara_soc'),
                           ('ara_tb.dut.i_ara_soc.i_system','ara_system'),
                           ('ara_tb.dut.i_ara_soc.i_system.i_ara','ara'),
                           (old.PREFIX[:-1],'vlsu'),(old.PREFIX+'i_addrgen','addrgen')]:
        require(design.hierarchy[scope].get('name') == expected, 'Actual compiled RTL instance chain changed')
    result=copy.deepcopy(prior); result['pins']=pins; pins[str(PRIOR)]=PRIOR_SHA
    result['explicit_semantic_derivation']=derived
    result['prior_proof_seal']=PRIOR_SHA
    result['old_EL_inventory_scope']='Frozen proof01 1166-file inventory; prepared-only padding candidate01 is not native approval/application'
    result['repeatability_policy']='Closed historical inventory plus fail-closed check of new EL; only exact source-bound unexecuted self candidates classified separately'
    for filename in ('prove_vlsu_address_padding770_v2.py','test_prove_vlsu_address_padding770_v2.py'):
        p=Path(__file__).with_name(filename); pins[str(p)]=old.digest(p)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(not args.output.exists(),'Fresh proof successor only')
    result=evidence()
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(old.digest(args.output))
