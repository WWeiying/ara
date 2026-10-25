"""Host-only binding/schema mutations; never execute an RTL or target kernel."""
import copy
from fractions import Fraction
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split import combine_v2 as c
from verification.akv.quantized_kv.tail_split import query_reference_v2 as q


def captured(offset=0):
    return struct.pack('<1536f', *[((i % 31) - 15) * 0.125 + offset for i in range(1536)])


def elf(payload):
    names = b'\0attention_query\0'
    string_offset = 64 + len(payload)
    symbol_offset = string_offset + len(names)
    symbols = bytes(24) + struct.pack('<IBBHQQ', 1, 0x10, 0, 1, 0x80000000, 0)
    section_offset = symbol_offset + len(symbols)
    header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01' + bytes(9),
                         2, 243, 1, 0, 0, section_offset, 0, 64, 0, 0, 64, 4, 0)
    sections = [bytes(64), struct.pack('<IIQQQQIIQQ', 0, 1, 2, 0x80000000, 64, len(payload), 0, 0, 4, 0),
                struct.pack('<IIQQQQIIQQ', 0, 3, 0, 0, string_offset, len(names), 0, 0, 1, 0),
                struct.pack('<IIQQQQIIQQ', 0, 2, 0, 0, symbol_offset, len(symbols), 2, 1, 8, 24)]
    return header + payload + names + symbols + b''.join(sections)


def record(kind, visible, same=False):
    source = captured(0 if same or kind == 'q4_0' else 0.25)
    quantized = q.reconstruct(source)
    identity = 'a' * 64
    return dict(kind=kind, prefixes=[visible], state='PASS', post_pins_match=True,
        independent_protocol_checked=True, simulator_exit_code=0, commands=c.command_count(visible),
        native_calls=2, outputs_per_trial=768, trials=[{}, {}, {}],
        query_hex={str(h): quantized[h*136:(h+1)*136].hex() for h in range(6)},
        elf_sha256=identity, source_pins_sha256=identity,
        run_identity=dict(directory=f'/runs/{kind}-{visible}', result_sha256=identity,
            status_sha256=identity, source_pins_sha256=identity, elf_sha256=identity),
        query_binding=dict(schema=c.SCHEMA, kind=kind, capture_query=str(c.query_path(kind)),
            capture_bytes=6144, selected_heads=[0, 1, 2, 3, 4, 5], selected_bytes=3072,
            quantized_bytes=816, reference=c.REFERENCE, independent_fflags=False,
            capture_sha256=q.digest(source), selected_sha256=q.digest(source[:3072]),
            elf_query_sha256=q.digest(source), quantized_sha256=q.digest(quantized),
            quantizer_source=str(c.QUANTIZER), quantizer_function_sha256=c.FUNCTION_SHA,
            quantizer_object=str(c.QUANT_OBJECT), quantizer_source_sha256=identity,
            quantizer_object_sha256=identity, capture_receipt_sha256=identity))


def matrix(same=False):
    return [record(k, v, same) for k in ('q4_0', 'q8_0') for v in (5, 33)]


class MatrixTests(unittest.TestCase):
    def test_different_and_equal_profiles_legal(self):
        for same in (False, True):
            rows = matrix(same)
            self.assertEqual(rows[0]['query_hex'] == rows[2]['query_hex'], same)
            result = c.validate_matrix(rows)
            self.assertEqual(result['acceptance'], 'TAIL_SPLIT_COMBINED_PASS_V2')
            self.assertEqual(result['commands'], 24)
            self.assertEqual(result['records'], rows)
            self.assertEqual(result['records'][0]['query_hex'] == result['records'][2]['query_hex'], same)
            self.assertFalse(result['original_timeout_reclassified'])
            self.assertFalse(result['independent_query_fflags'])

    def test_within_profile_drift_even_with_updated_digest(self):
        rows = matrix()
        rows[1]['query_hex'] = copy.deepcopy(rows[2]['query_hex'])
        rows[1]['query_binding']['quantized_sha256'] = q.digest(c.joined_query(rows[1]))
        with self.assertRaisesRegex(ValueError, 'within profile'):
            c.validate_matrix(rows)

    def test_capture_swap_and_missing_binding(self):
        for field in ('kind', 'capture_query'):
            rows = matrix()
            rows[0]['query_binding'][field] = rows[2]['query_binding'][field]
            with self.assertRaises(ValueError):
                c.validate_matrix(rows)
        rows = matrix()
        del rows[0]['query_binding']
        with self.assertRaises(ValueError):
            c.validate_matrix(rows)

    def test_missing_profile_prefix_counts_and_typed_flags(self):
        rows = matrix()
        for bad in (rows[:3], [rows[0], rows[0], rows[2], rows[3]]):
            with self.assertRaises(ValueError):
                c.validate_matrix(bad)
        for key, value in (('kind', 'q6_K'), ('prefixes', [True]), ('prefixes', [128]),
                           ('commands', 0), ('native_calls', 1), ('outputs_per_trial', 0),
                           ('trials', [{}, {}]), ('post_pins_match', 1),
                           ('independent_protocol_checked', False), ('simulator_exit_code', False),
                           ('state', 'TIMEOUT')):
            bad = matrix()
            bad[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                c.validate_matrix(bad)

    def test_legacy_namespace_unchanged(self):
        from verification.akv.quantized_kv.tail_split import combine as original
        self.assertIsNot(original, c.legacy)
        self.assertIsNot(original.checked_run, c.checked_run)
        self.assertEqual(c.s.digest(c.HERE / 'combine.py'), c.LEGACY_SHA)


class ReferenceTests(unittest.TestCase):
    def test_exact_rounding_and_constant_rows(self):
        self.assertEqual([q.nearest(Fraction(x, 2)) for x in (-7, -5, -3, 3, 5, 7)],
                         [-4, -2, -2, 2, 2, 4])
        self.assertEqual(q.normal_rne(1 + Fraction(1, 1 << 24)), 1)
        self.assertEqual(q.normal_rne(1 + Fraction(3, 1 << 24)), 1 + Fraction(1, 1 << 22))
        scale = struct.unpack('<f', struct.pack('<f', 1/127))[0]
        for value, integer in ((1.0, 127), (-1.0, -127)):
            raw = struct.pack('<1536f', *([value] * 1536))
            block = struct.pack('<e', scale) + struct.pack('<32b', *([integer] * 32))
            self.assertEqual(q.reconstruct(raw), block * 24)

    def test_reject_out_of_domain(self):
        for value in (0.0, float('nan'), float('inf'), 2.0**-140, 2.0**-110, 2.0**127):
            with self.subTest(value=value), self.assertRaises(ValueError):
                q.reconstruct(struct.pack('<1536f', *([value] * 1536)))
        with self.assertRaises(ValueError):
            q.reconstruct(bytes(3072))

    def test_elf_symbol_bytes_and_malformed_input(self):
        raw = captured()
        data = elf(raw)
        self.assertEqual(q.elf_query(data), raw)
        for bad in (data[:30], data[:-1], data.replace(b'attention_query', b'attention_wrong'),
                    data[:4] + b'\x01' + data[5:]):
            with self.assertRaises(ValueError):
                q.elf_query(bad)

    def test_checked_run_binding_and_wrong_elf_capture(self):
        production = c.QUANTIZER.read_bytes()
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            cap, quantizer, obj = root / 'captures', root / 'quants.c', root / 'quants.o'
            cap.mkdir()
            quantizer.write_bytes(production)
            obj.write_bytes(b'explicit-host-fixture-not-code')
            with patch.multiple(c, CAPTURE=cap, QUANTIZER=quantizer, QUANT_OBJECT=obj):
                row = record('q4_0', 5)
                query = c.query_path('q4_0')
                query.parent.mkdir(parents=True)
                query.write_bytes(captured())
                meta = query.with_suffix('.json')
                meta.write_text(json.dumps(dict(type='f32', shape=[128, 1, 12, 1],
                                  strides=[4, 512, 512, 6144], nbytes=6144)))
                receipt = cap / 'result.json'
                receipt.write_text(json.dumps(dict(captures={'q4_0': {
                    'file_sha256': c.s.hashes([query, meta])}})))
                build = root / 'build'
                build.mkdir()
                program = build / 'tail_attention.elf'
                program.write_bytes(elf(captured()))
                (build / 'commands.json').write_text(json.dumps([dict(argv=['cc', '-nostdlib', str(obj)])]))
                run = root / 'run'
                run.mkdir()
                row.update(build=str(build), elf_sha256=c.s.digest(program))
                for filename in ('result.json', 'status.json'):
                    (run / filename).write_text('{}')
                original_result_bytes = (run / 'result.json').read_bytes()
                pins = c.s.hashes([query, meta, receipt, quantizer, obj])
                report = dict(elf=str(program), elf_sha256=c.s.digest(program))
                with patch.object(c, 'old_checked_run', return_value=(row, report, pins)) as delegated:
                    bound, _build, _pins = c.checked_run(run)
                    delegated.assert_called_once_with(run)
                    self.assertEqual(bound['query_binding']['quantized_sha256'], q.digest(q.reconstruct(captured())))
                    self.assertEqual((run / 'result.json').read_bytes(), original_result_bytes)
                    program.write_bytes(elf(captured(0.25)))
                    report['elf_sha256'] = row['elf_sha256'] = c.s.digest(program)
                    with self.assertRaisesRegex(ValueError, 'profile capture'):
                        c.checked_run(run)


if __name__ == '__main__':
    unittest.main()
