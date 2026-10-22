"""Preserve both frozen plans; only terminal publication module changes in03."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;OLD=HERE/'vcs_m8_plan02';NEW=HERE/'vcs_m8_plan03'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sha(OLD/'replay.py')=='bcdb7357e55131e61ef345f1260799d878cab98c44b5a5eca3e0ba3c92a89741'
    assert sha(OLD/'prepared01/plan.json')=='41e1c8521953dcc5322dacf10de1ee53d59c3f7d1187118c63136f46aababe7a'
    NEW.mkdir(exist_ok=False)
    for name in ('replay.py','checker.py','reset_profile.json','test_terminal.py','run_host.py'):
        (NEW/name).write_bytes((OLD/name).read_bytes())
    proof=json.loads((OLD/'successor_proof.json').read_text())
    for path in [OLD/'prepared01/plan.json',OLD/'prepared01/ready.json',OLD/'prepared01/dryrun_gate.json',
            OLD/'terminal_publish.py',OLD/'replay.py',OLD/'host03.json',OLD/'host_terminal03/execution.json',
            OLD/'host_terminal03/stdout.log',OLD/'host_terminal03/stderr.log',Path(__file__)]:
        proof['old_input_pins'][str(path)]=sha(path)
    proof['also_preserved_plan02_sha256']=sha(OLD/'prepared01/plan.json')
    proof['changed_from02']='terminal_publish.py only; exact worker/checker/reset copied'
    proof['old_input_pins'][str(OLD/'successor_proof.json')]=sha(OLD/'successor_proof.json')
    proof['old_input_pins'][str(OLD/'worker_delta.diff')]=sha(OLD/'worker_delta.diff')
    (NEW/'successor_proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    (NEW/'worker_delta.diff').write_bytes((OLD/'worker_delta.diff').read_bytes())
    print('MATERIALIZED_PUBLICATION_ONLY03',NEW)


if __name__=='__main__':main()
