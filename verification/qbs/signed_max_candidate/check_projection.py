"""Strict signed-max ABBA protocol adapter to the established projection checks."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'combined_zvfh_m4/projection/check.py'
spec = importlib.util.spec_from_file_location('accepted_projection_checks', BASE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
ORDER = ['accepted_vector', 'signed_max', 'signed_max', 'accepted_vector']


def check_output(text, contract):
    base.require(contract['order'] == ORDER and contract['both_vector_paths_required'] is True,
                 'Wrong vector-versus-vector contract')
    lines = text.splitlines()
    positions = [i for i, line in enumerate(lines) if line.strip().startswith('Q8K_CURRENT_TRIAL ')]
    base.require(len(positions) == 4, 'Missing/extra ABBA trials')
    for trial, position in enumerate(positions):
        words = lines[position].strip().split()
        fields = [word.partition('=') for word in words[1:]]
        base.require(all(sep and value for _, sep, value in fields), 'Malformed field')
        values = {key: value for key, _, value in fields}
        base.require(len(values) == len(fields) and set(values) == set(base.FIELDS), 'Field schema')
        base.require(values['id'] == str(trial) and values['path'] == ORDER[trial] and
                     values['used'] == '1', 'Both actual vector paths must succeed')
        # Adapt only validated path witnesses. All numerical, CSR, traffic,
        # integrity and timing checks remain those of the accepted harness.
        values['path'] = 'canonical' if trial in (1, 2) else 'generic'
        values['used'] = '1' if trial in (1, 2) else '0'
        lines[position] = words[0]+' '+' '.join(key+'='+values[key] for key, _, _ in fields)
    result = base.check_output('\n'.join(lines), contract)
    for row in result['trials']:
        row['path'] = ORDER[row['id']]
        row['used'] = 1
    result['sums'] = dict(accepted_vector=result['sums']['generic'], signed_max=result['sums']['canonical'])
    result['scope'] = 'Accepted vector versus signed-max vector, same-ELF projection; not full model'
    return result


def main():
    import hashlib
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'log', 'trace', 'uvm'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    build = json.loads((args.build/'build.json').read_text())
    manifest = args.build/'manifest.json'
    base.require(build['state'] == 'READY' and sha(manifest) == build['manifest_sha256'], 'Build drift')
    base.require(all(sha(path) == value for path, value in json.loads(manifest.read_text()).items()),
                 'Input/artifact drift')
    result = check_output(args.log.read_text(), json.loads((args.build/'contract.json').read_text()))
    result['traffic'] = base.check_trace(args.trace)
    uvm = json.loads(args.uvm.read_text())
    base.require(uvm['status'] == 'PASS' and not uvm.get('issues'), 'UVM checks failed')
    result.update(state='PASS', log_sha256=sha(args.log), trace_sha256=sha(args.trace),
                  uvm_sha256=sha(args.uvm), manifest_sha256=sha(manifest))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
