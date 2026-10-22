from context import *
entry=read(HERE/'ENTRY.json')
for p,h in entry['pins'].items():require(sha(p)==h,'Sealed original entry input drift '+p)
pins=dict(entry['pins'])
for p in HERE.iterdir():
    if p.is_file() and p.name!='ENTRY02.json':pins[str(p.resolve())]=sha(p)
h=read(HERE/'HOST03.json');receipt=read(HERE/'host03_execution.json')
require(h['tests']==5 and h['status']=='PASS_SHORT_PARSER_BOUNDARIES' and h['errors']==h['failures']==0
    and receipt['actual_wait_returncode']==0 and not receipt['timed_out'],'Actual short boundary tests')
require(read(HERE/'host03_preflight.json')==read(HERE/'host03_postflight.json'),'Boundary pins unchanged')
entry.update(pins=pins,executor=str(HERE/'reference02.py'),executor_sha256=sha(HERE/'reference02.py'),
    schema='sentinel_mask_reference_entry02',original_HOLD_entry_sha256=sha(HERE/'ENTRY.json'),
    parser_nonempty_unmatched_rejected=True,cost_gate_counter='firmware_to_HTIF',
    short_parser_host_sha256=sha(HERE/'HOST03.json'),actual_parser_host_execution_sha256=sha(HERE/'host03_execution.json'))
save(HERE/'ENTRY02.json',entry)
print('ENTRY02',sha(HERE/'ENTRY02.json'),'pins',len(pins),flush=True)
