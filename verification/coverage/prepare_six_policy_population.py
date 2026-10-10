"""Prepare one explicit sealed population; no EDA launch entry is provided."""
import argparse
import copy
import json
from pathlib import Path
from types import FunctionType

import apply_branch_combo_six_717 as frozen
import audit_uvm_no_traffic_719_snapshot as snapshot

SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_prepare_six_policy_population.py')
SCHEMA = 'six-policy-explicit-historical-population-v1'
require = frozen.require


def private(function, **bindings):
    return FunctionType(function.__code__, dict(function.__globals__, **bindings), function.__name__,
                        function.__defaults__, function.__closure__)


def review_function(population, digest):
    require(type(population) is int and population >= 717, 'Explicit integer population>=717 required')
    function = frozen.latest_review
    constants = function.__code__.co_consts
    require(sum(type(c) is int and c == 717 for c in constants) == 1, 'Frozen population guard boundary changed')
    code = function.__code__.replace(co_consts=tuple(population if type(c) is int and c == 717 else c for c in constants))
    return FunctionType(code, dict(function.__globals__, sha=digest), function.__name__)


def validate_population(bitmap, status, inputs, population):
    require(type(population) is int and population >= 717, 'Invalid population')
    require(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            status['aggregate_passed'] == population == len(bitmap['tests']) == len(set(bitmap['tests'])),
            'Only exact sealed PASS population; FAIL/TIMEOUT/candidate forbidden')
    design = str(frozen.OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb')
    require(inputs == [design, *bitmap['tests']], 'Ordered admission membership differs')
    require(status.get('new_RTL_signoff', False) is False and status.get('rtl_changed', False) is False,
            'Not a fixed-image admission')


class Context:
    def __init__(self, admission, seal, population):
        self.admission = Path(admission).absolute()
        require(self.admission.parent == frozen.OUT and self.admission.resolve() == self.admission,
                'Direct workspace admission required')
        require(type(population) is int and population >= 717, 'Explicit integer population required')
        self.seal, self.population = seal, population
        self.mapping = {str(snapshot.HARDWARE_PATH): str(snapshot.SNAPSHOT)}

    def digest(self, path):
        return frozen.sha(self.mapping.get(str(Path(path).absolute()), path))

    def pin(self, pins, path, expected=None):
        original = str(Path(path).absolute())
        if original in self.mapping:
            require(expected in (None, snapshot.SNAPSHOT_SHA), 'Snapshot cannot stand for different compiled bytes')
            return frozen.pin(pins, self.mapping[original], snapshot.SNAPSHOT_SHA)
        return frozen.pin(pins, path, expected)

    def qualification(self, pins=None):
        qualified = private(frozen.qualification707, sha=self.digest, pin=self.pin)()
        mapped = {}
        for path, digest in qualified['pins'].items():
            self.pin(mapped, path, digest)
        qualified['pins'] = mapped
        if pins is not None:
            pins.update(mapped)
        return qualified

    def admission_inputs(self, base, raw_report, raw_seal, evidence_seal, pins):
        require(Path(base).absolute() == self.admission and Path(raw_report).absolute() == frozen.RAW_GEOMETRY and
                raw_seal == frozen.RAW_GEOMETRY_SEAL, 'Explicit admission/reference binding differs')
        admitted = frozen.load_sealed(self.pin(pins, self.admission / 'admission-manifest.json', self.seal), self.seal)
        require(admitted['output'] == str(self.admission), 'Admission output ownership differs')
        mandatory = {'combined-bits.json', 'combined-inputs.txt', 'status.json', 'evidence-pins.json'}
        require(all(str(self.admission / name) in admitted['output_pins'] for name in mandatory), 'Unsealed admission outputs')
        for path, digest in admitted['output_pins'].items():
            self.pin(pins, path, digest)
        require(admitted['output_pins'][str(self.admission / 'evidence-pins.json')] == evidence_seal,
                'Evidence ledger not bound by admission seal')
        evidence = json.loads((self.admission / 'evidence-pins.json').read_bytes())
        for path, digest in evidence.items():
            self.pin(pins, path, digest)
        bitmap = json.loads((self.admission / 'combined-bits.json').read_bytes())
        status = json.loads((self.admission / 'status.json').read_bytes())
        inputs = (self.admission / 'combined-inputs.txt').read_text().splitlines()
        validate_population(bitmap, status, inputs, self.population)
        anchor = frozen.load_sealed(self.pin(pins, frozen.LATEST / 'admission-manifest.json', frozen.LATEST_SEAL), frozen.LATEST_SEAL)
        anchor_input = frozen.LATEST / 'combined-inputs.txt'
        self.pin(pins, anchor_input, anchor['output_pins'][str(anchor_input)])
        require(inputs[:718] == anchor_input.read_text().splitlines(), 'Sealed formal717 prefix lost/reordered')
        for path, digest in bitmap['input_hashes'].items():
            require(evidence.get(path) == digest, 'Member bytes missing from sealed admission ledger')
            self.pin(pins, path, digest)
        for relative, digest in bitmap['design'].items():
            self.pin(pins, Path(inputs[0]) / 'snps/coverage/db' / relative, digest)
        geometry = frozen.load_sealed(self.pin(pins, frozen.RAW_GEOMETRY / 'population-verification.json', raw_seal), raw_seal)
        require(geometry['status'] == 'VERIFIED_HISTORICAL_RAW_REPORT' and geometry['admitted_tests'] == 715 and
                geometry['current_RTL_signoff'] is False, 'Unqualified geometry reference')
        for name in ('summary.csv', 'inputs.txt', 'selected_tests.txt'):
            path = frozen.RAW_GEOMETRY / name
            self.pin(pins, path, geometry['pins'][str(path)])
        require((frozen.RAW_GEOMETRY / 'inputs.txt').read_text().splitlines() == inputs[:716],
                'Reference design/prefix differs; no historical percentages inherited')
        tests = []
        for root in inputs[1:]:
            root = Path(root)
            require(root.resolve() == root and not root.is_symlink(), 'Aliased member VDB')
            directories = list((root / 'snps/coverage/db/testdata').iterdir())
            require(len(directories) == 1 and directories[0].is_dir(), 'Not singleton admitted VDB')
            tests.append(str(root.with_suffix('') / directories[0].name))
        require(len(set(tests)) == self.population, 'Duplicate explicit native test identity')
        return bitmap, inputs, tests, self.population

    def source_binding(self, pins):
        self.pin(pins, frozen.SCRIPT)
        self.pin(pins, frozen.TCL)
        self.pin(pins, Path(snapshot.__file__).resolve())
        self.pin(pins, snapshot.BUILD, snapshot.BUILD_SHA)
        build = json.loads(snapshot.BUILD.read_bytes())
        require(build[str(snapshot.HARDWARE_PATH)] == snapshot.SNAPSHOT_SHA, 'Compiled snapshot mapping differs')
        self.pin(pins, snapshot.SNAPSHOT, snapshot.SNAPSHOT_SHA)
        return dict(compiled_hardware_source=str(snapshot.HARDWARE_PATH), snapshot=str(snapshot.SNAPSHOT),
                    sha256=snapshot.SNAPSHOT_SHA, build_manifest_sha256=snapshot.BUILD_SHA,
                    current_dispatcher_read=False)

    def namespace(self):
        return dict(SCRIPT=SCRIPT, TCL=TCL, TEST=TEST, sha=self.digest, pin=self.pin,
                    baseline_inputs=self.admission_inputs, qualification707=self.qualification,
                    latest_review=review_function(self.population, self.digest), check_config=self.check_config)

    def check_config(self, config, output):
        # This hook also runs before frozen prepare writes config.json.
        if config['schema'] == 'six-policy-historical717-qualified707-v1':
            config['schema'] = SCHEMA
            config['admission_manifest_sha256'] = self.seal
            config['source_snapshot_binding'] = self.source_binding(config['pins'])
            config['frozen_prepare_code_sha256'] = frozen.sha(frozen.SCRIPT)
            config['report_scope'] = 'Historical fixed image diagnostic; no new RTL signoff or final waiver approval'
            config['one_population_snapshot_per_run'] = True
            config['automatic_population_following'] = False
            config['failure_exclusion_basis'] = 'Only exact members of explicit sealed PASS admission; never scan/append candidate or retry directories'
            config['launch_approved'] = False
            population_file = output / 'population-selection.tcl'
            population_file.write_text('set six_expected_count %d\nset six_admission_count %d\n' % (self.population, self.population))
            config['pins'][str(population_file)] = frozen.sha(population_file)
        require(config['schema'] == SCHEMA and config['admission_manifest_sha256'] == self.seal and
                config['population'] == self.population and config['one_population_snapshot_per_run'] and
                not config['automatic_population_following'] and not config['launch_approved'], 'Wrong successor contract')
        require(config['source_snapshot_binding'] == self.source_binding(config['pins']) and
                config['frozen_prepare_code_sha256'] == frozen.sha(frozen.SCRIPT) and
                str(snapshot.HARDWARE_PATH) not in config['pins'], 'Live dispatcher substituted for compiled snapshot')
        expected = 'set six_expected_count %d\nset six_admission_count %d\n' % (self.population, self.population)
        require((output / 'population-selection.tcl').read_text() == expected, 'Tcl population gate changed')
        facade = copy.deepcopy(config)
        facade['schema'] = 'six-policy-historical717-qualified707-v1'
        private(frozen.check_config, **self.namespace())(facade, output)


def prepare(output, context):
    manifest = frozen.load_sealed(context.admission / 'admission-manifest.json', context.seal)
    evidence_seal = manifest['output_pins'][str(context.admission / 'evidence-pins.json')]
    private(frozen.prepare, **context.namespace())(output, context.admission, frozen.RAW_GEOMETRY,
                                                 frozen.RAW_GEOMETRY_SEAL, evidence_seal)
    config = json.loads((output / 'config.json').read_bytes())
    require(config['population'] == context.population and config['targets'] == 5808 and config['protected'] == 13562,
            'Exact native target/protection population differs')
    print(json.dumps(dict(output=str(output), config_sha256=frozen.sha(output / 'config.json'),
                          admission_manifest_sha256=context.seal, population=context.population,
                          targets=config['targets'], protected=config['protected'], pins=len(config['pins']),
                          status='PREPARED_NO_DVE_PARENT_REVIEW_REQUIRED', launched=False)))


def read_config(output, seal):
    config = frozen.load_sealed(output / 'config.json', seal)
    context = Context(config['admitted_base'], config['admission_manifest_sha256'], config['population'])
    context.check_config(config, output)
    return context, config


def verify(output, seal):
    context, config = read_config(output, seal)
    marker = 'SIX_POPULATION_SELECTION_ADAPTER_INSTALLED'
    adapter = lambda path: (path / 'DVEfiles/dve_gui.log').read_text().splitlines().count(marker) == 1
    result = private(frozen.verify_artifacts, **dict(context.namespace(), log_adapter=adapter))(output, config)
    result['status'] = 'HISTORICAL_EXPLICIT_POPULATION_SIX_POLICY_REPORT_NOT_FINAL_WAIVER_APPROVAL'
    result['application_approval'] = False
    result['admission_manifest_sha256'] = context.seal
    result['config_sha256'] = seal
    import apply_qbs_rooted_701 as q
    summaries = {stage: q.previous.pilot.corrected.summary(output / ('summary_' + stage + '.csv'))
                 for stage in ('raw', 'applied', 'reset')}
    scope = 'ara_tb.dut.i_ara_soc.i_system'
    result['actual_population_i_system'] = {stage: rows[scope] for stage, rows in summaries.items()}
    result['historical_percentages_inherited'] = False
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--admission', type=Path)
    parser.add_argument('--admission-seal')
    parser.add_argument('--population', type=int)
    parser.add_argument('--seal')
    args = parser.parse_args(argv)
    output = args.output.absolute()
    require(output.parent == frozen.OUT and output.resolve() == output and not output.is_symlink(), 'Unsafe output')
    if args.mode == 'prepare':
        require(args.admission and args.admission_seal and args.population and not args.seal, 'Explicit admission/seal/population required')
        prepare(output, Context(args.admission, args.admission_seal, args.population))
    else:
        require(args.seal and args.admission is None and args.admission_seal is None and args.population is None, 'Only sealed output accepted')
        if args.mode == 'check':
            _, config = read_config(output, args.seal)
            print(json.dumps(dict(status='PREPARED_INPUTS_NATIVE_PROTECTION_VERIFIED_NO_DVE', population=config['population'])))
        else:
            print(json.dumps(verify(output, args.seal), indent=2))


if __name__ == '__main__':
    main()
