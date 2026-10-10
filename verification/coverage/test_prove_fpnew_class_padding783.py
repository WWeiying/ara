import unittest
import prove_fpnew_class_padding783 as p


def params(fmt=2, vec=1, true=1, width=64):
    fp = (32, 64, 16)[fmt]
    lanes = width // fp if vec else 1
    return dict(Width=width, FpFormat=fmt, EnableVectors=vec, TrueSIMDClass=true,
                NUM_LANES=lanes, FP_WIDTH=fp, SIMD_WIDTH=width//lanes,
                CLASS_VEC_BITS=min(lanes*8, width))


class Geometry(unittest.TestCase):
    def test_exact_parameter_definition_binding(self):
        E = p.ET
        module = E.fromstring('<srcdef id="-27" name="fpnew_opgroup_fmt_slice"/>')
        shape = E.fromstring('<root><tgldef id="-27" chksum="123" name="fpnew_opgroup_fmt_slice ( parameter Width=64 )"/></root>')
        self.assertEqual(p.bound_definition(module, '123', shape).get('chksum'), '123')
        with self.assertRaises(ValueError): p.bound_definition(module, '124', shape)
        shape.append(E.fromstring(E.tostring(shape[0])))
        with self.assertRaises(ValueError): p.bound_definition(module, '123', shape)

    def test_half_protects_all_four_low10_slots(self):
        expected = {lane*16+b for lane in range(4) for b in range(10,16)}
        for field in p.FIELDS:
            self.assertEqual(p.zero_bits(params(), field), expected)

    def test_single_preserves_second_class_slot(self):
        z = p.zero_bits(params(0), 'slice_class_result')
        self.assertEqual(z, set(range(10,32)) | set(range(42,64)))
        self.assertFalse(z & set(range(32,42)))

    def test_double(self):
        self.assertEqual(p.zero_bits(params(1), 'slice_class_result'), set(range(10,64)))

    def test_compressed_scalar_mux_preserves_bits8_9(self):
        q = params(0, 0, 0)
        self.assertEqual(p.zero_bits(q, 'slice_vec_class_result'), set(range(8,64)))
        self.assertEqual(p.zero_bits(q, 'slice_class_result'), set(range(10,64)))

    def test_compressed_vector_mux_union(self):
        self.assertEqual(p.zero_bits(params(2,1,0), 'slice_class_result'), set(range(32,64)))

    def test_bad_derived_parameter(self):
        q = params(); q['SIMD_WIDTH'] = 32
        with self.assertRaisesRegex(ValueError, 'derived geometry'):
            p.zero_bits(q, p.FIELDS[0])

    def test_fp8_and_unknown_field_rejected(self):
        q = params(); q['FpFormat'] = 3
        with self.assertRaises(ValueError): p.zero_bits(q, p.FIELDS[0])
        with self.assertRaises(ValueError): p.zero_bits(params(), 'result_o')

    def test_frozen_source_and_mutations(self):
        s = (p.m.ROOT/'hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv').read_text()
        pkg = (p.m.ROOT/'hardware/deps/fpnew/src/fpnew_pkg.sv').read_text()
        p.source_guard(s, pkg)
        for bad in (s.replace("SIMD_WIDTH-10] = '0", "SIMD_WIDTH-10] = '1"),
                    s.replace(' : lane_class_mask[0]', ' : slice_regular_result'),
                    s + '\nassign slice_class_result = result_o;'):
            with self.assertRaises(ValueError): p.source_guard(bad, pkg)
        with self.assertRaises(ValueError): p.source_guard(s, pkg.replace('enum logic [9:0]', 'enum logic [10:0]'))


if __name__ == '__main__': unittest.main()
