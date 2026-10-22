"""Freeze actual typed16 software, Host, lowerings and the single reference."""
import json
from pathlib import Path
import prepare as p
HERE=p.HERE
require=p.old.require
status=json.loads((HERE/'software_status.json').read_text())
require(status['actual_paired_host_runs']==20 and status['scope']['SEW']==16 and status['scope']['CAP']==512,
    'Actual typed16 software Host')
pins=json.loads((HERE/'pins.json').read_text())
for path,digest in pins.items():require(p.sha(path)==digest,'Original software pin drift '+path)
for variant in ('original','packed'):
    for mutation in range(10):
        receipt=json.loads((HERE/f'host_{variant}/case{mutation}.log.exit.json').read_text())
        require(receipt['returncode']==(-4 if mutation==8 else 0 if mutation==0 else 1),'Actual compiledC Host exit')
local=json.loads((HERE/'reference_host_result.json').read_text())
outcome=json.loads((HERE/'reference_host_execution.json').read_text())
require(local['status']=='PASS' and local['tests']==7 and local['errors']==local['failures']==0 and
    outcome['actual_wait_returncode']==0 and outcome['timed_out'] is False,'Actual lifecycle/type boundary Host')
for path in HERE.rglob('*'):
    if path.is_file() and path.suffix!='.pyc':pins[str(path)]=p.sha(path)
p.save(HERE/'entry.json',dict(status='SEALED_TYPED16_SOFTWARE_PENDING_INDEPENDENT_ONE_REFERENCE_REVIEW',
    SEW=16,LMUL='m8',CAP=512,vtype=11,calls=4095,results=2096640,guards=8190,helper_instructions=53235,
    checked_bytes=1028,tail_bytes=4,physical_input_bytes=2048,physical_output_bytes=2052,
    upper_physical_mask_zero_bytes=64,original_sentinel='005b',dictionary_blocks=3598,ROM_bytes=369886,
    pins=pins,software_status_sha256=p.sha(HERE/'software_status.json'),proof_sha256=p.sha(HERE/'proof.json'),
    hard_reference_steps=4000000,reference_timeout_s=120,max_raw_bytes=768*1024**2,cost_target=3000000,
    one_attempt=True,DUT_authorized=False,original_C_bytes_recovered=False,original_Linux_history_closed=False))
print('SEALED_ENTRY',p.sha(HERE/'entry.json'),'pins',len(pins))
