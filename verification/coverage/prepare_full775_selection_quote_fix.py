"""Fresh775 selection-only quoting successor; no EDA and no new exclusions."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import prepare_full775_cached as cached

p = cached.original
SOURCE = p.life.OUT / 'native-full775-cached-parent-20261007-01'
SOURCE_SHA = '9ebd932ebdc0dfba10f12b4d6d5ddd988be7d2af067650eab91fb4f653b8286f'
RECEIPT_SHA = 'd8db6ac5aa50b9d06f990dee5fb84980b3af64a61b8a218168c3e9f7fefb654d'
HERE = Path(__file__).resolve()
TEST = HERE.with_name('test_prepare_full775_selection_quote_fix.py')
TCLSH = Path('/usr/bin/tclsh')


def specs(contract):
    scopes = contract['scopes']
    p.need(len(scopes) == len(set(scopes)) == 12, 'Exact12 Branch720 scopes')
    result = []
    for scope in scopes:
        p.need(re.fullmatch(r'ara_tb\.dut\.i_ara_soc\.i_system\.i_ara\.gen_lanes\[[0-3]\]'
                           r'\.i_lane\.i_operand_queues\.i_operand_queue_(mask_m|slide_addrgen_a|st_mask_a)', scope),
               'Unexpected Branch scope')
        points = [r for r in contract['branch_inventory'] if r['scope'] == scope]
        p.need(all(type(r['target']) is bool for r in points), 'Exact Boolean target role')
        keys = [r['selector'] for r in points]
        targets = [r['selector'] for r in points if r['target']]
        p.need(len(keys) == len(set(keys)) == 101 and len(targets) == len(set(targets)) == 60 and
               len(set(keys)-set(targets)) == 41 and all(re.fullmatch(r'[0-9]+,[0-9]+', k) for k in keys),
               'Complete101 / targets60 / protected41 per scope')
        result.append((scope, keys, targets))
    p.need(len(contract['branch_inventory']) == 1212, 'No extra scope inventory')
    return result


def declarations(contract):
    atom = p.prior.tcl_atom
    result = {}
    for scope, keys, targets in specs(contract):
        for variable, values in [('op1144_keys', keys), ('op1144_targets', targets)]:
            varname = '::%s(%s)' % (variable, scope)
            rhs = '[list %s]' % ' '.join(map(atom, values))
            old = 'set %s %s\n' % (varname, rhs)
            new = 'set %s %s\n' % (atom(varname), rhs)
            result[old] = new
    return result


def fixed_selection(text, contract):
    replacements = declarations(contract)
    seen = set(); lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith('set ::op1144_keys(') or line.startswith('set ::op1144_targets('):
            p.need(line in replacements and line not in seen, 'Unbound/changed/duplicate Branch declaration')
            seen.add(line); lines.append(replacements[line])
        else:
            p.need(not re.match(r'^\s*set\s+\S*op1144_(keys|targets)', line),
                   'Unknown alternative Branch declaration')
            lines.append(line)
    p.need(seen == set(replacements) and len(seen) == 24, 'All24 declarations required')
    return ''.join(lines)


def host_check(text, contract):
    # The entire actual generated selection is evaluated INSIDE a procedure,
    # matching the consumer's source context. No unknown command fallback.
    p.need(all(not line.strip() or line.startswith(('set ', 'lappend ', '#'))
               for line in text.splitlines()), 'Declaration-only host input')
    atom = p.prior.tcl_atom
    expected = ' '.join('[list %s [list %s] [list %s]]' %
        (atom(scope), ' '.join(map(atom, keys)), ' '.join(map(atom, targets)))
        for scope, keys, targets in specs(contract))
    script = 'proc actual_consumer_context {} {\n' + text + '\n}\nactual_consumer_context\n'
    script += 'set expected [list %s]\n' % expected
    script += r'''
set scopes {}
set members 0
set targets 0
set protected 0
foreach spec $expected {
    set scope [lindex $spec 0]
    lappend scopes $scope
    if {![info exists ::op1144_keys($scope)] || ![info exists ::op1144_targets($scope)]} {error "Missing array member"}
    if {$::op1144_keys($scope) ne [lindex $spec 1]} {error "Exact complete keys differ"}
    if {$::op1144_targets($scope) ne [lindex $spec 2]} {error "Exact target roles differ"}
    incr members [llength $::op1144_keys($scope)]
    incr targets [llength $::op1144_targets($scope)]
    foreach key $::op1144_keys($scope) {
        if {[lsearch -exact $::op1144_targets($scope) $key] < 0} {incr protected}
    }
}
if {$::op1144_scopes ne $scopes} {error "Scope order differs"}
foreach array {op1144_keys op1144_targets} {
    if {[lsort [array names ::$array]] ne [lsort $scopes]} {error "Unexpected array owner"}
}
puts "FULL_SELECTION_PASS 24 $members $targets $protected"
'''
    # Tcl stdin interactive evaluation can continue after errors. Catch the
    # WHOLE script and explicitly exit nonzero instead of relying on stderr.
    wrapper = 'if {[catch {\n'+script+'\n} message options]} {puts stderr [dict get $options -errorinfo]; exit 1}\n'
    run = subprocess.run([str(TCLSH)], input=wrapper, text=True, capture_output=True, timeout=20)
    p.need(run.returncode == 0 and run.stderr == '' and
           run.stdout == 'FULL_SELECTION_PASS 24 1212 720 492\n', 'Actual full-selection Tcl failure: '+run.stderr[:1000])
    return dict(status='ACTUAL_FULL_SELECTION_IN_PROC_HOST_PASS', array_members=24,
                all_coordinates=1212, targets=720, protected=492,
                stdout=run.stdout, stderr=run.stderr, returncode=run.returncode,
                selection_sha256=hashlib.sha256(text.encode()).hexdigest(),
                tclsh=str(TCLSH), tclsh_sha256=p.life.digest(TCLSH), EDA_launched=False)


def prepare(output):
    p.need(output.parent == p.life.OUT and not output.exists(), 'Fresh independent output only')
    p.life.check({str(path): sha for path, sha in cached.FROZEN.items()})
    source = p.life.read_bound(SOURCE/'config.json', SOURCE_SHA)
    receipt = p.life.read_bound(SOURCE/'cached-prepare-receipt.json', RECEIPT_SHA)
    p.need(receipt['status'] == 'ORIGINAL_FULL775_CHECK_PASS_NO_EDA' and receipt['config_seal'] == SOURCE_SHA and
           receipt['original_final_check'] is True and source['schema'] == p.SCHEMA and source['population'] == 775 and
           source['successor_entry'] == str(Path(p.__file__).resolve()), 'Exact successful cached preparation authority')
    originals = {}
    for name in ('selection.tcl', 'combined.el', 'inputs.txt'):
        path=SOURCE/name; p.need(p.life.digest(path)==source['pins'][str(path)], 'Immutable source product')
        originals[name]=path.read_bytes()
    fixed = fixed_selection(originals['selection.tcl'].decode(), source['branch720'])
    host = host_check(fixed, source['branch720'])
    dependencies={str(path):p.life.digest(path) for path in (HERE,TEST,TCLSH,Path(cached.__file__).resolve())}
    dependencies.update({str(SOURCE/'config.json'):SOURCE_SHA,str(SOURCE/'cached-prepare-receipt.json'):RECEIPT_SHA})
    c=dict(source, output=str(output))
    pins=p.prior.merge(source['pins'],dependencies)
    output.mkdir()
    products=dict(originals, **{'selection.tcl':fixed.encode(),
                               'selection-host-proof.json':(json.dumps(host,indent=2)+'\n').encode()})
    for name, data in products.items():
        path=output/name
        with path.open('xb') as stream:stream.write(data)
        pins[str(path)]=p.life.digest(path)
    c['pins']=pins
    c['selection_quote_fix']=dict(adapter=str(HERE),source_config=str(SOURCE/'config.json'),source_seal=SOURCE_SHA,
                                  source_receipt_seal=RECEIPT_SHA,declarations=24, changed_EL_coordinates=0,
                                  host_proof=str(output/'selection-host-proof.json'))
    p.life.save(output/'config.json',c)
    seal=p.life.digest(output/'config.json')
    p.check(output,seal)
    p.life.check(dependencies)
    final=dict(status='FULL775_QUOTED_SELECTION_ORIGINAL_CHECK_PASS_NO_EDA',config_seal=seal,
               source_config_seal=SOURCE_SHA,original_entry=c['successor_entry'],changed_declarations=24,
               unchanged_EL=True,unchanged_population=775,host_proof=host,
               pins=p.prior.merge(dependencies,{str(output/'config.json'):seal},
                                 {str(output/name):pins[str(output/name)] for name in products}),EDA_launched=False)
    p.life.save(output/'selection-quote-fix-receipt.json',final)
    print(json.dumps(dict(status=final['status'],output=str(output),config_seal=seal,
                          receipt_seal=p.life.digest(output/'selection-quote-fix-receipt.json'))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();prepare(args.output.resolve())
