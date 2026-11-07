"""Host-only tests; no simulator, target execution, or evidence rewriting.

Inherited parser fixtures are synthetic schema/accounting data, not measurements.
Only their CSR rows are constructed for the new contract. Manifest fixtures below
are in-memory mocks, not receipts. The build05/raw FAIL fixture is read unchanged
and SHA-checked; it must never be accepted as successor evidence.
"""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


legacy = module('q6_csr_legacy_tests', 'test_profile.py')
check = module('q6_csr_check', 'check_successor.py')
builder = module('q6_csr_build', 'build_csr_successor.py')


class SuccessorParserTests(legacy.ParserTests):
    """Run predecessor strictness tests against synthetic successor records."""

    def setUp(self):
        super().setUp()
        self.lines = [
            (line.replace('fcsr_quant=1 ', 'fcsr_quant=1 vcsr_quant=2 vstart_quant=0 ')
             .replace('vcsr_after=0', 'vcsr_after=2'))
            if line.startswith('Q6_DECODE_CSR ') else line for line in self.lines]
        self.text = '\n'.join(self.lines)

    def parse(self, text=None):
        return check.parse_log(self.text if text is None else text, 'test', self.q8, self.expected)

    def test_csr_guards_and_work_rejected(self):
        # Same legacy cases, with final vcsr=2 as the valid successor baseline.
        for old, new in (
            ('fcsr_before=0', 'fcsr_before=1'), ('vcsr_before=0', 'vcsr_before=2'),
            ('vstart_before=0', 'vstart_before=1'), ('fcsr_quant=1', 'fcsr_quant=16'),
            ('fcsr_after=1', 'fcsr_after=17'), ('vstart_after=0', 'vstart_after=1'),
            ('vcsr_after=2', 'vcsr_after=1'), ('vl_after=32', 'vl_after=16'),
            ('vtype_after=208', 'vtype_after=209'), ('quant_calls=1', 'quant_calls=0'),
            ('plan_calls=1', 'plan_calls=2'), ('execute_calls=1', 'execute_calls=2'),
            ('guard_errors=0', 'guard_errors=1'), ('k_elements=2048', 'k_elements=1024'),
            ('hex=' + 'a5'*64, 'hex=' + 'a5'*63+'a4'),
        ):
            with self.subTest(old=old):
                self.reject(self.text.replace(old, new, 1))

    def test_exact_rne_preserved_on_both_trials(self):
        for t in self.parse()['trials']:
            self.assertEqual((t['csr']['vcsr_quant'], t['csr']['vcsr_after']), (2, 2))
            self.assertEqual((t['csr']['vstart_quant'], t['csr']['vstart_after']), (0, 0))
            self.assertEqual(t['csr']['vcsr_after'] & 1, 0)

    def test_all_other_vcsr_values_rejected_even_if_preserved(self):
        # 0/4/6 select other rounding; all odd values set sticky saturation.
        for value in (0, 1, 3, 4, 5, 6, 7, 8, 10, 2**64-1):
            for trial in range(2):
                with self.subTest(vcsr=value, trial=trial):
                    lines = list(self.lines)
                    i = next(i for i, s in enumerate(lines)
                             if s.startswith(f'Q6_DECODE_CSR trial={trial} '))
                    lines[i] = lines[i].replace('vcsr_quant=2', f'vcsr_quant={value}')
                    lines[i] = lines[i].replace('vcsr_after=2', f'vcsr_after={value}')
                    self.reject('\n'.join(lines))

    def test_quant_and_after_must_match_without_reset_or_saturation(self):
        for field in ('vcsr_quant', 'vcsr_after'):
            for value in (0, 1, 3, 4, 5, 6, 7):
                with self.subTest(field=field, value=value):
                    self.reject(self.text.replace(f'{field}=2', f'{field}={value}', 1))

    def test_quant_vstart_and_new_schema_fail_closed(self):
        for field, value in (('vstart_quant', 0), ('vcsr_quant', 2)):
            token = f'{field}={value}'
            for replacement in ('', token+' '+token, f'{field}=-1', f'{field}=0x2'):
                with self.subTest(field=field, replacement=replacement):
                    self.reject(self.text.replace(token, replacement, 1))
        self.reject(self.text.replace('vstart_quant=0', 'vstart_quant=1', 1))

    def test_allowed_fcsr_flags_still_preserved(self):
        for value in range(4):
            self.parse(self.text.replace('fcsr_quant=1', f'fcsr_quant={value}')
                       .replace('fcsr_after=1', f'fcsr_after={value}'))

    def test_errors_two_never_accepted_with_new_csr_schema(self):
        self.reject(self.text.replace('errors=0 trials=2', 'errors=2 trials=2'))

    def test_old_schema_rejected_even_with_zero_footer(self):
        fixture = legacy.ParserTests()
        fixture.setUp()
        self.reject(fixture.text)

    def run_fixture(self, text, identity_drift=False):
        """Mock build I/O only; the complete log goes unmodified to check_run."""
        manifest = dict(build_id='test', q8_expected='q8', expected='expected',
                        elf_sha256='elf', source_pins_sha256='pins')
        reads = []

        def read_text(path):
            reads.append(path)
            self.assertEqual(path, Path('fixture.log'))
            return text

        identity_reads = []

        def digest(path):
            if Path(path) == HERE / 'check_successor.py':
                identity_reads.append(path)
                return 'changed' if identity_drift and len(identity_reads) > 1 else 'identity'
            return 'fixture'

        with mock.patch.object(check, 'check_build', return_value=manifest), \
             mock.patch.object(Path, 'read_text', autospec=True, side_effect=read_text), \
             mock.patch.object(Path, 'read_bytes', side_effect=[self.q8, self.expected]), \
             mock.patch.object(check, 'digest', side_effect=digest):
            result = check.check_run(Path('fixture.log'), Path('fixture_build'))
        self.assertEqual(reads, [Path('fixture.log')])
        return result

    def test_unified_check_run_interface(self):
        result = self.run_fixture(self.text)
        self.assertEqual(result['state'], 'PASS')
        self.assertEqual(result['checker_identity'], dict(
            path=str(HERE / 'check_successor.py'), sha256='identity', entrypoint=check.CHECKER_API))
        self.assertEqual(result['successor_reason'], check.SUCCESSOR_REASON)
        self.assertEqual(result['csr_contract'], check.CSR_CONTRACT)
        for text in (self.text.replace('bits=00000000', 'bits=00000001', 1),
                     '\n'.join(self.lines[:-1]),
                     self.text.replace('fcsr_after=1', 'fcsr_after=17', 1),
                     self.text.replace('hex='+'a5'*64, 'hex='+'a4'*64, 1),
                     self.text.replace('errors=0 trials=2', 'errors=2 trials=2')):
            with self.assertRaises(ValueError):
                self.run_fixture(text)

    def test_checker_identity_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Checker identity changed'):
            self.run_fixture(self.text, identity_drift=True)


class BuildManifestTests(unittest.TestCase):
    """In-memory trusted/untrusted manifests exercise real check_build gates."""

    def setUp(self):
        self.path = Path('/fixture/build.json')
        names = (*check.SUCCESSOR_FILES, 'main.c', 'build.py', 'check.py',
                 'host_ref.c', 'test_profile.py', 'README.md')
        self.pins = {str(HERE / name): 'sha-'+name for name in names}
        self.pins[str(HERE / 'build.py')] = check.PARENT_BUILD_SHA256
        self.pins[str(HERE / 'check.py')] = check.PARENT_CHECK_SHA256
        self.digests = dict(self.pins)
        self.digests.update({'/fixture/elf': 'elf-sha', '/fixture/source-pins.json': 'pins-sha',
                             '/fixture/commands.json': 'commands-sha'})
        self.commands = [dict(label='compile-main', argv=[
            'gcc', '-c', str(HERE / 'main_csr_successor.c'), '-o', '/fixture/main.o'])]
        self.receipt = dict(
            state='BUILT_NOT_EXECUTED', performance_measured=False,
            post_pins_match=True, reused_objects=0, elf='/fixture/elf', elf_sha256='elf-sha',
            source_pins='/fixture/source-pins.json', source_pins_sha256='pins-sha',
            artifacts={'/fixture/commands.json': 'commands-sha'},
            checker_entry=[sys.executable, '-B', str(HERE / 'check_successor.py'),
                           '--build', str(self.path), '--log', '<run.vcs.log>',
                           '--output', '<new authorized output.json>'],
            checker_api=check.CHECKER_API,
            csr_contract=copy.deepcopy(check.CSR_CONTRACT), successor_reason=check.SUCCESSOR_REASON,
            parent_builder=dict(path=str(HERE / 'build.py'), sha256=check.PARENT_BUILD_SHA256),
            measurement_source=str(HERE / 'main_csr_successor.c'),
            capture_scope=dict(phase='decode', position=40, m=1, k=2048, n=64,
                               weight_profile=2, trials=2, commands_per_trial=2))

    def validate(self):
        documents = {str(self.path): self.receipt, '/fixture/source-pins.json': self.pins,
                     '/fixture/commands.json': self.commands}
        with mock.patch.object(Path, 'read_text', autospec=True,
                               side_effect=lambda p: json.dumps(documents[str(p)])), \
             mock.patch.object(Path, 'is_file', return_value=True), \
             mock.patch.object(check, 'digest', side_effect=lambda p: self.digests[str(p)]):
            return check.check_build(self.path)

    def test_successor_manifest_accepted(self):
        self.assertEqual(self.validate(), self.receipt)

    def test_every_old_and_new_helper_required_and_unchanged(self):
        for name in list(self.pins):
            with self.subTest(name=name):
                sha = self.pins.pop(name)
                with self.assertRaises(ValueError):
                    self.validate()
                self.pins[name] = sha
                self.digests[name] = 'drift'
                with self.assertRaises(ValueError):
                    self.validate()
                self.digests[name] = sha

    def test_repinning_changed_predecessors_rejected(self):
        for name in ('build.py', 'check.py'):
            key = str(HERE / name)
            sha = self.pins[key]
            self.pins[key] = self.digests[key] = 'repinned-drift'
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Predecessor identity'):
                self.validate()
            self.pins[key] = self.digests[key] = sha

    def test_csr_contract_reason_and_checker_metadata_required(self):
        for key in ('csr_contract', 'successor_reason', 'checker_entry', 'checker_api',
                    'parent_builder', 'measurement_source'):
            saved = self.receipt.pop(key)
            with self.subTest(missing=key), self.assertRaises((ValueError, KeyError)):
                self.validate()
            self.receipt[key] = saved
        for quant_value in (0, 3, 4, 6):
            self.receipt['csr_contract']['quant']['vcsr'] = quant_value
            with self.subTest(vcsr=quant_value), self.assertRaises(ValueError):
                self.validate()
        self.receipt['csr_contract'] = copy.deepcopy(check.CSR_CONTRACT)
        for key, value in (
            ('successor_reason', 'reinterpret old FAIL'), ('checker_api', 'other'),
            ('measurement_source', str(HERE / 'main.c')),
            ('parent_builder', dict(path=str(HERE / 'build.py'), sha256='other')),
        ):
            saved = self.receipt[key]
            self.receipt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate()
            self.receipt[key] = saved
        self.receipt['checker_entry'][2] = str(HERE / 'check.py')
        with self.assertRaisesRegex(ValueError, 'checker entry'):
            self.validate()

    def test_old_receipt_integrity_gates_preserved(self):
        for key, value in (('state', 'PASS'), ('performance_measured', True),
                           ('post_pins_match', False), ('reused_objects', 1),
                           ('elf_sha256', 'other'), ('source_pins_sha256', 'other')):
            saved = self.receipt[key]
            self.receipt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate()
            self.receipt[key] = saved
        self.digests['/fixture/commands.json'] = 'drift'
        with self.assertRaisesRegex(ValueError, 'artifact drift'):
            self.validate()

    def test_actual_compile_must_route_exactly_one_main(self):
        original = copy.deepcopy(self.commands)
        for commands in ([], original*2, [dict(label='compile-main', argv=[
                'gcc', '-c', str(HERE / 'main.c'), '-o', '/fixture/main.o'])]):
            self.commands = commands
            with self.subTest(commands=commands), self.assertRaises(ValueError):
                self.validate()

    def test_build_shape_and_scope_unchanged(self):
        for key, value in (('phase', 'prefill'), ('position', 0), ('m', 4), ('k', 1024),
                           ('n', 32), ('weight_profile', 1), ('trials', 1),
                           ('commands_per_trial', 1)):
            saved = self.receipt['capture_scope'][key]
            self.receipt['capture_scope'][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'build shape'):
                self.validate()
            self.receipt['capture_scope'][key] = saved


class BuilderAndSourceTests(unittest.TestCase):
    """Static source checks and mocked compiler dispatch never launch a tool."""

    def test_parent_hash_checked_before_module_execution(self):
        with mock.patch.object(Path, 'read_bytes', return_value=b'untrusted'), \
             mock.patch.object(importlib.util, 'spec_from_file_location') as load:
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                builder.load_parent()
            load.assert_not_called()

    def test_only_exact_original_main_routed(self):
        b = builder.Builder(Path('/unused'))
        flags = ['-O3']
        sources = [HERE / 'main.c', HERE / 'host_ref.c', Path('/sdk/qbs_runtime.c'),
                   Path('/sdk/qbs_native_riscv.c'), Path('/llama/quants.c'),
                   Path('/other/main.c'), Path('/sdk/crt0.S')]
        original_class = builder.Builder.__mro__[1]
        with mock.patch.object(original_class, 'compile', autospec=True) as compile:
            for i, source in enumerate(sources):
                obj = Path(f'/unused/object{i}.o')
                b.compile('gcc', flags, source, obj)
                routed = HERE / 'main_csr_successor.c' if source == HERE / 'main.c' else source
                compile.assert_called_with(b, 'gcc', flags, routed, obj)
        self.assertEqual(builder.parent.HERE, HERE)
        self.assertEqual(builder.parent.ROOT, HERE.parents[3])

    def test_c_work_and_boundaries_unchanged(self):
        old = (HERE / 'main.c').read_text()
        new = (HERE / 'main_csr_successor.c').read_text()
        trial = new.split('void q6_decode_trial(', 1)[1].split('static uint32_t bits', 1)[0]
        self.assertNotRegex(trial, r'\bcsrw\w*\b')
        self.assertEqual(trial.count('fence rw, rw'), 1)
        self.assertEqual(re.findall(r'const uint64_t t[0-4] = cycles\(\);', old),
                         re.findall(r'const uint64_t t[0-4] = cycles\(\);', new))
        self.assertEqual(new.count('csrwi vcsr, 0'), 1)  # Original pre-trial reset only.
        self.assertIn('const uint64_t t1 = cycles();\n  /* Quant CSR reads', trial)
        self.assertIn('r->vcsr_quant != 2 || r->vstart_quant', new)
        self.assertIn('r->vcsr_after != r->vcsr_quant || r->vstart_after', new)
        # The work/guard/numerical/planning and timestamp-output blocks are verbatim.
        for start, end in (
            ('  qbs_status_t status =', '  *r ='),
            ('    q6_decode_trial(t,', '    errors +='),
            ('    printf("Q6_DECODE_TRIAL', '    printf("Q6_DECODE_CSR'),
            ('    printf("Q6_DECODE_WORK', '  return errors != 0;'),
        ):
            self.assertEqual(old.split(start, 1)[1].split(end, 1)[0],
                             new.split(start, 1)[1].split(end, 1)[0])

    def test_all_non_csr_parser_checks_mechanically_identical(self):
        class MaskCSR(ast.NodeTransformer):
            def visit_If(self, node):
                node = self.generic_visit(node)
                if ast.dump(node.test) == ast.dump(ast.parse(
                        "line.startswith('Q6_DECODE_CSR')", mode='eval').body):
                    node.body = [ast.Pass()]
                return node

        def parser_ast(name):
            tree = ast.parse((HERE / name).read_text())
            fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'parse_log')
            return ast.dump(MaskCSR().visit(fn))

        self.assertEqual(parser_ast('check.py'), parser_ast('check_successor.py'))


class OriginalFailureEvidenceTests(unittest.TestCase):
    """Pinned, read-only real build05 and failed VCS log; not a PASS fixture."""
    OUT = builder.parent.OUT
    OLD_BUILD = OUT / 'chain_q6_build_20261107_05'
    FAILURE = OUT / 'chain_profile_runs_20261107_01/q6'
    RAW_SHA256 = 'ebdaadf53c3c6ffdaa84767540410a603f5849bdd11fe88876e52d6be1902fc5'

    def test_raw_original_failure_rejected_unchanged(self):
        path = self.FAILURE / 'work/run.vcs.log'
        self.assertEqual(check.digest(path), self.RAW_SHA256)
        receipt = json.loads((self.OLD_BUILD / 'build.json').read_text())
        with self.assertRaisesRegex(ValueError, 'CSR schema/order'):
            check.parse_log(path.read_text(), receipt['build_id'],
                            Path(receipt['q8_expected']).read_bytes(),
                            Path(receipt['expected']).read_bytes())
        with self.assertRaises(ValueError):
            check.check_run(path, self.OLD_BUILD)
        self.assertEqual(json.loads((self.FAILURE / 'result.json').read_text())['state'], 'FAIL')
        self.assertEqual(check.digest(path), self.RAW_SHA256)

    def test_predecessor_still_rejects_its_original_log(self):
        with self.assertRaisesRegex(ValueError, 'CSR contract failure'):
            legacy.check.check_run(self.FAILURE / 'work/run.vcs.log', self.OLD_BUILD)

    def test_root_cause_source_and_disassembly(self):
        receipt = json.loads((self.OLD_BUILD / 'build.json').read_text())
        quant = self.OLD_BUILD / 'quant-disassembly.log'
        self.assertEqual(check.digest(quant), receipt['artifacts'][str(quant)])
        self.assertRegex(quant.read_text().splitlines()[78], r'80000a24:.*csrwi\s+vxrm,1')
        source = self.OLD_BUILD / 'inputs/llama/ggml/src/ggml-cpu/arch/riscv/quants.c'
        pins = json.loads((self.OLD_BUILD / 'source-pins.json').read_text())
        self.assertEqual(check.digest(source), pins[str(source)])
        self.assertIn('__riscv_vnclip_wx_i16m4(v_i32, 0, __RISCV_VXRM_RNE, vl)', source.read_text())
        self.assertIn('__riscv_vnclip_wx_i8m2(v_i16, 0, __RISCV_VXRM_RNE, vl)', source.read_text())


if __name__ == '__main__':
    unittest.main()
