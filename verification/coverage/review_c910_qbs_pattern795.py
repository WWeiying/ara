"""Independent static selector review and finite QBS scale-contrast hypothesis."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value(bits, precision=23, bias=127):
    exp = (bits >> precision) & (2 * bias + 1)
    mant = bits & ((1 << precision) - 1)
    assert exp != 2 * bias + 1, 'Finite operands only'
    power = (exp or 1) - bias - precision
    number = Fraction(mant + ((1 << precision) if exp else 0))
    return number * (Fraction(2) ** power)


def round32(number):
    assert number >= 0
    if not number:
        return 0, 0
    exponent = number.numerator.bit_length() - number.denominator.bit_length()
    if number < Fraction(2) ** exponent:
        exponent -= 1
    unit = Fraction(2) ** max(exponent - 23, -149)
    scaled = number / unit
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    twice = 2 * remainder
    rounded = quotient + int(twice > scaled.denominator or
                             (twice == scaled.denominator and quotient & 1))
    exact = rounded * unit
    inexact = exact != number
    if exact < Fraction(2) ** -126:
        bits = int(exact / (Fraction(2) ** -149))
    else:
        exp = exact.numerator.bit_length() - exact.denominator.bit_length()
        if exact < Fraction(2) ** exp:
            exp -= 1
        assert exp <= 127, 'No overflow in this finite proposal'
        bits = ((exp + 127) << 23) | (int(exact / (Fraction(2) ** (exp - 23))) - (1 << 23))
    return bits, int(inexact) | (2 if inexact and bits < 0x00800000 else 0)


def main():
    pins = {}
    def bound(path, expected=None):
        path = Path(path)
        actual = digest(path)
        assert expected is None or actual == expected, str(path)
        pins[str(path)] = actual
        return json.loads(path.read_text())
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = bound(book_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    vendor = 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'
    sources = [vendor + 'ct_vfdsu_' + name + '.v' for name in
               ('prepare', 'srt', 'srt_radix16_with_sqrt', 'srt_radix16_bound_table')]
    sources += ['hardware/src/vlsu/qbs/' + name + '.sv' for name in
                ('qbs_read_engine', 'qbs_compute_engine', 'qbs_profile_engine_int', 'qbs_fp_accumulator')]
    sources += ['hardware/include/qbs_pkg.sv', 'hardware/deps/fpnew/src/fpnew_fma.sv']
    for name in sources:
        path = ROOT / name
        assert digest(path) == book[str(path)], name
        pins[str(path)] = book[str(path)]
    plan = bound(OUT / 'scalar-c910-pattern-plan795-agent-20261008-01.json')
    bound(OUT / plan['typed_inventory'], plan['typed_inventory_sha256'])
    rank = bound(OUT / 'qbs-dynamic795-independent-agent-20261008-02.json',
                 '915eab42d44cd61bfb05a0625a618eee0d75cdc71638d1adaf27bb1691aeaacf')
    for path, sha in rank['input_pins'].items():
        assert digest(Path(path)) == sha, path
        pins[path] = sha
    selectors = []
    for index in range(64):
        for tail in (0x155555555555, 0x2aaaaaaaaaaa):
            assert tail < 1 << 46
            fraction = (index << 46) | tail
            selector = (((1 << 52) | fraction) << 3) >> 49
            assert selector == 64 + index
            selectors.append(selector)
    assert all(selectors.count(index) == 2 for index in range(64, 128))
    assert round32(Fraction(1)) == (0x3f800000, 0)
    assert round32(Fraction(2) ** -150) == (0, 3)
    assert round32(Fraction(2) ** -149) == (1, 0)
    scales = [round32(value(w, 10, 15) * value(a)) for w, a in
              ((0x3d55, 0x3f555555), (0x0401, 0x00800001))]
    results = []
    for order in ((0, 1), (1, 0)):
        acc, flags = 0, 0
        for index in order:
            acc, status = round32(value(scales[index][0]) * 8 + value(acc))
            flags |= scales[index][1] | status
        results.append(dict(order=list(order), positive_result=hex(acc),
                            negative_result=hex(acc | 0x80000000), fflags=flags))
    names = {'product_shifted', 'sum_shifted', 'sum_sticky_bits',
             'addend_sticky_bits', 'addend_after_shift'}
    targets = [r for r in rank['objects'] if r['scope'].endswith('.i_fma') and r['name'] in names]
    assert len(targets) == 5 and sum(r['missing_count'] for r in targets) == 264
    pins[str(Path(__file__).resolve())] = digest(Path(__file__).resolve())
    result = dict(status='STATIC_SOURCE_BOUND_HYPOTHESIS_NOT_PREFLIGHTED_NOT_NATIVE_QUALIFIED',
        input_pins=pins, baseline=795, baseline_seal=rank['baseline_seal'],
        EL_seal=rank['EL_seal'], scalar_review=dict(normal_DIV_selector='64 + fraction[51:46]',
        cells=128, selectors=list(range(64, 128)), occurrences_each=2,
        source_path=['prepare:615,622 normal significand', 'srt:712,716 initial selector',
                     'radix16_with_sqrt:348..352 reset/initial/SQRT update'],
        conclusion='Normal DIV mapping PASS; SQRT iterative selector and actual Toggle gains not proved'),
        qbs=dict(shape=dict(M=1, N=2, K=512), weight_profile='Q4_K', activation_profile='Q8_K',
        layout='ROW_MAJOR, DIRECT; aligned valid PMA buffers; two descriptors with reversed K-block scale order',
        bytes=dict(weight=576, activation=584), subgroup='Each of 8 subgroups: activation [1,-1,0*30]; row0 weights [1,0,0*30], row1 [0,1,0*30]; subscales1, minimum0, dmin0. Dot totals +8/-8; aux0.',
        scales=[dict(weight_fp16='0x3d55', activation_fp32='0x3f555555', rounded_fp32=hex(scales[0][0]), fflags=scales[0][1]),
                dict(weight_fp16='0x0401', activation_fp32='0x00800001', rounded_fp32=hex(scales[1][0]), fflags=scales[1][1])],
        exact_rational_gold=results, targets=targets, missing_capacity_upper_bound=264,
        source_path=['profile_engine_int:398..412,648..653 subtotal correction;459..465 result',
                     'compute_engine:511..518 FP request', 'fp_accumulator:237..266 operation/operand mux;357..378 scale decode;398..421 accumulation',
                     'fpnew_fma:285..317 exponent difference and saturated alignment;337..359 product/addend;518..567 normalization/sticky'],
        hypothesis='Dense then tiny: addend anchored. Tiny then dense: product anchored, tiny retained addend shifted into sticky. Both signs supplied by two output columns.',
        probes=['per-owner request index/first/dot/aux/scales', 'accepted FP operands/op and exponent_difference/addend_shamt',
                'five target fields and owned result/status', 'VRF writes, destination snapshots, guards, fflags/FCSR and complete memory/retirement comparison'],
        gate='Packed blocks/descriptors and exact custom owner oracle must preflight before any runtime. No software build or simulation done.',
        recommendation='Not a demonstrated >1000-direction stimulus. Do not launch based on capacity alone.'),
        HOLD=['segment ara_resp resp/cause/tval: concurrent scalar response domain not closed',
              'read-engine fault addresses: previous canonical failure remains record-only',
              'cast generic-format widths/special results: not selected entropy targets',
              'MDA/partial EL: no fabricated binary or native direction mapping',
              'sequence/performance counters: no long-loop stimulus'],
        measured_gain=None, official_denominator=None, EDA_started=False, RTL_changed=False)
    output = OUT / 'c910-qbs-pattern795-independent-review-agent-20261008-01.json'
    assert not output.exists()
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(output, digest(output), json.dumps(results))


if __name__ == '__main__':
    main()
