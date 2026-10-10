"""One authorized systemd foreground lifecycle; no retry or runtime source edits."""
import argparse
import json
from pathlib import Path

import qbs_eight735_runtime_v8 as runtime
import run_six_policy_population as exclusive
import prepare_six_policy_population as population

SCRIPT = Path(__file__).resolve()
EXPECTED_SEAL = 'b5c194b1c6a4a2cc0080ad7a4e82afefeeb424f6575e81c12398e820338c24b8'
frozen = population.frozen
require = runtime.f.require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    args = parser.parse_args()
    output = exclusive.output_path(args.output)
    require(args.seal == EXPECTED_SEAL, 'Only the once-authorized prepared seal')
    exclusive.unstarted(output)
    exclusive.claim_once(output, args.seal, 'foreground')
    authority = dict(source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL',
        runtime_seal=args.seal, output=str(output), launch_count=1, native_budget_seconds=14400,
        automatic_retry=False, final_application=False,
        runner=str(SCRIPT), runner_sha256=runtime.f.sha(SCRIPT),
        lifecycle=str(frozen.SCRIPT), lifecycle_sha256=runtime.f.sha(frozen.SCRIPT))
    with (output/'authorization-receipt.json').open('x') as stream:
        json.dump(authority, stream, indent=2); stream.write('\n')
    try:
        _, _, context, config = runtime.verify(output, args.seal)

        def authority_guard():
            require(runtime.f.sha(SCRIPT) == authority['runner_sha256'] and
                    runtime.f.sha(frozen.SCRIPT) == authority['lifecycle_sha256'], 'Lifecycle code drift')
            require(runtime.f.sha(output/runtime.NAME) == args.seal, 'Prepared runtime seal drift')

        def read_adapter(path, seal):
            require(path == output and seal == args.seal, 'Foreground configuration binding differs')
            authority_guard()
            return config

        def verify_adapter(path, actual):
            require(path == output and actual == config, 'Terminal configuration differs')
            authority_guard()
            return runtime.inspect(output, args.seal)

        def write_adapter(path, value):
            frozen.write(path, value)
            if path == output/'live-identity.json':
                with (output/'started.json').open('x') as stream:
                    json.dump(dict(status='ACTUAL_DVE_EXECUTABLE_VERIFIED',
                        authorization_source=authority['source'], runtime_seal=args.seal,
                        actual_executable=value, automatic_retry=False), stream, indent=2)
                    stream.write('\n')

        bindings = dict(context.namespace(), TIMEOUT=runtime.BUDGET, read_config=read_adapter,
                        verify_artifacts=verify_adapter, write=write_adapter)
        population.private(frozen.run, **bindings)(output, args.seal)
    except Exception as exc:
        frozen.write(output/'status.json', dict(status='HOLD', reason=repr(exc),
            runtime_seal=args.seal, application_approval=False, automatic_retry=False))
        raise
    state = json.loads((output/'status.json').read_bytes())
    require(state['status'] == 'FRESH735_EIGHT_PLUS_QBS1792_V8_QUALIFIED_NOT_APPLICATION',
            'Terminal qualification failed/HOLD; no retry')


if __name__ == '__main__': main()
