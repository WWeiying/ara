"""Rank raw zero slots outside approved trusted IP; not native waived percentages."""
import argparse
import json
from pathlib import Path

import report_trusted_ip797 as report


def collect():
    review = report.life.read_bound(report.REVIEW, report.REVIEW_SHA)
    report.policy.validate(review)
    admission = report.s.OUT / 'vsmul-saturation-offline-admitted797-parent-20261008-01'
    manifest = report.life.read_bound(admission / 'admission-manifest.json',
        '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4')
    path = admission / 'combined-toggle-bits.json'
    seal = manifest['output_pins'][str(path)]
    bitmap = report.life.read_bound(path, seal)
    rows = []
    baseline = report.life.read_bound(report.BASE / 'qualification.json', report.BASE_QUAL)
    el_path = report.BASE / 'applied.el'
    el_sha = baseline['output_pins'][str(el_path)]
    report.need(report.life.digest(el_path) == el_sha, 'Qualified inherited EL')
    other, _ = report.s.semantic(el_path.read_text())
    inherited_wholes = sorted({x[0] for x in other if x[3] == 'WHOLE_SCOPE'})
    roots = list(review['minimal_recommended_roots']) + inherited_wholes
    for scope, row in bitmap.items():
        if not report.policy.inside(scope) or report.owned(scope, roots):
            continue
        width, value = int(row['width']), int(row['bits'], 16)
        report.need(width >= 0 and 0 <= value < (1 << width), 'Exact raw bitmap bounds')
        hit = bin(value).count('1')
        rows.append(dict(scope=scope, checksum=row['checksum'], serialized_slots=width,
                         raw_hit_slots=hit, raw_zero_slots=width - hit))
    rows.sort(key=lambda x: (-x['raw_zero_slots'], x['scope']))
    return dict(status='RAW797_OUTSIDE_TRUSTED_IP_PRIORITY_DIAGNOSTIC',
        population=797, bitmap=str(path), bitmap_sha256=seal,
        review_sha256=report.REVIEW_SHA,
        inherited_EL_sha256=el_sha, inherited_whole_scopes_removed=inherited_wholes,
        precise_point_exclusions_subtracted=False, official_denominator_verified=False,
        caveat='Raw serialized slots identify investigation priority only. Existing point waivers remain in these counts. No percentage or native bit-direction approval is inferred.',
        instances=rows)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    result = collect()
    report.life.save(a.output, result)
    print(json.dumps(result['instances'][:12], indent=2))
