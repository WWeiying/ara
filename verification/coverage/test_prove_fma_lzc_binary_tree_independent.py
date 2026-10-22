"""Independent abstract-child audit and negative tests; no HDL/EDA execution."""
import copy
import itertools
import json
import unittest
import prove_fma_lzc_binary_tree as proof


def merge(left_index, right_index, left_domain, right_domain, prefer_left=True):
    if left_domain and right_domain and max(left_domain) >= min(right_domain):
        raise ValueError('Children overlap or priority order reversed')
    if left_index is not None and left_index not in left_domain:
        raise ValueError('Left selected index outside domain')
    if right_index is not None and right_index not in right_domain:
        raise ValueError('Right selected index outside domain')
    actual = (left_index if left_index is not None else right_index) if prefer_left else (right_index if right_index is not None else left_index)
    expected = min((x for x in (left_index,right_index) if x is not None), default=None)
    if actual != expected:
        raise ValueError('Priority counterexample')
    return expected


def independent_tree(width):
    size = 1 << (width-1).bit_length()
    domains, empty_indices = {}, {}
    def visit(heap, first, extent):
        domain = list(range(first,min(first+extent,width))) if first < width else []
        if extent == 2:
            fallback = first+1 if len(domain)==2 else first if domain else 0
        else:
            left=visit(heap*2+1,first,extent//2)
            right=visit(heap*2+2,first+extent//2,extent//2)
            if left+right != domain: raise ValueError('Domain partition')
            fallback=empty_indices[heap*2+2]
        domains[heap]=domain;empty_indices[heap]=fallback
        return domain
    visit(0,0,size)
    return domains,empty_indices


def boundary(instance):
    p=instance['parameters'];width=p['WIDTH'];levels=(width-1).bit_length();size=1<<levels
    if p != dict(WIDTH=width,MODE=1,CNT_WIDTH=levels,**{'gen_lzc.NumLevels':levels}):
        raise ValueError('Unexpected elaborated parameters')
    fields={f['name']:f for f in instance['internal_candidates']}
    expected={
        'gen_lzc.index_lut':[[width-1,0],[levels-1,0]],
        'gen_lzc.in_tmp':[[width-1,0]],
        'gen_lzc.sel_nodes':[[size-1,0]],
        'gen_lzc.index_nodes':[[size-1,0],[levels-1,0]]}
    if set(fields)!=set(expected):raise ValueError('Internal scope changed')
    for name,dims in expected.items():
        if fields[name]['dimensions']!=dims:raise ValueError('Compiled dimensions mismatch')
        bits=1
        for left,right in dims:bits*=left-right+1
        if fields[name]['logical_bits']!=bits:raise ValueError('Incorrect capacity')
    ports=instance['protected_full_complement']
    if {f['name'] for f in ports}!={'in_i','cnt_o','empty_o'} or len(ports)!=3:
        raise ValueError('Port protection incomplete')
    expected_ports={'in_i':[[width-1,0]],'cnt_o':[[levels-1,0]],'empty_o':[]}
    if any(f['dimensions']!=expected_ports[f['name']] for f in ports):raise ValueError('Port width mismatch')
    return (width+size-1)*(levels+1),levels+1


class BinaryTreeReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.static=json.loads(proof.STATIC.read_bytes())

    def test_arbitrary_child_summaries_every_generated_merge(self):
        # Every binary child can summarize as empty or any selected real index.
        # Internal child details are irrelevant once the inductive invariant holds.
        for width in (25,51,109):
            p=proof.prove_width(width);domains,empty_indices=independent_tree(width)
            self.assertEqual({n['index']:n['domain'] for n in p['nodes']},domains)
            self.assertEqual({n['index']:n['empty_index'] for n in p['nodes']},empty_indices)
            for heap,domain in domains.items():
                if heap*2+2 not in domains:continue
                left,right=domains[heap*2+1],domains[heap*2+2]
                for a,b in itertools.product([None]+left,[None]+right):
                    merge(a,b,left,right)

    def test_leaf_binary_law_exhaustive_and_flip_mapping(self):
        for width in (25,51,109):
            p=proof.prove_width(width)
            for node in p['nodes']:
                if node['kind']=='ordered_priority_merge':continue
                for bits in itertools.product((0,1),repeat=len(node['domain'])):
                    selected=any(bits)
                    expected=next((j for j,b in zip(node['domain'],bits) if b),None)
                    actual=(node['domain'][0] if bits and bits[0] else node['empty_index'])
                    if selected:self.assertEqual(actual,expected)
            for bit in range(width):
                j=width-1-bit
                self.assertEqual(j,(width-(1<<bit).bit_length()))

    def test_reversed_priority_and_bad_domains_rejected(self):
        with self.assertRaises(ValueError):proof.merge_law(prefer_left=False)
        with self.assertRaises(ValueError):merge(0,2,[0,1],[2,3],prefer_left=False)
        with self.assertRaises(ValueError):merge(1,1,[0,1],[1,2])
        with self.assertRaises(ValueError):merge(2,None,[0,1],[2,3])

    def test_complete_assignment_excludes_exact_one_spare(self):
        for width in (25,51,109):
            p=proof.prove_width(width);spare=p['spare_index']
            assigned={n['index'] for n in p['nodes']}
            self.assertEqual(assigned,set(range(spare)))
            for heap in assigned:
                if 2*heap+1 in assigned:
                    self.assertIn(2*heap+2,assigned)
                    self.assertNotEqual(2*heap+2,spare)
            self.assertNotIn(spare,assigned)

    def test_actual32_shapes_23132_assigned_212_spare_96_ports(self):
        self.assertEqual(len(self.static['instances']),32)
        values=[boundary(i) for i in self.static['instances']]
        self.assertEqual(sum(v[0] for v in values),23132)
        self.assertEqual(sum(v[1] for v in values),212)
        self.assertEqual(sum(len(i['protected_full_complement']) for i in self.static['instances']),96)

    def test_bad_mode_count_width_spare_dimension_ports_rejected(self):
        i=self.static['instances'][0]
        variants=[]
        for key,value in (('MODE',0),('CNT_WIDTH',7),('gen_lzc.NumLevels',5)):
            bad=copy.deepcopy(i);bad['parameters'][key]=value;variants.append(bad)
        bad=copy.deepcopy(i);bad['internal_candidates'][2]['dimensions'][0][0]-=1;variants.append(bad)
        bad=copy.deepcopy(i);bad['protected_full_complement'].pop();variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError):boundary(bad)

    def test_frozen_source_and_changed_generate_rejected(self):
        source=(proof.ROOT/'hardware/deps/common_cells/src/lzc.sv').read_bytes()
        bench=(proof.ROOT/'verification/tests/fma_lzc_width_calibration.sv').read_bytes()
        proof.calibration.source_gate(source,bench)
        wrong=source.replace(b'l * 2 + 1',b'l * 2 + 2')
        self.assertNotEqual(source,wrong)
        with self.assertRaises(ValueError):proof.calibration.source_gate(wrong,bench)

    def test_empty_count_not_architectural_contract(self):
        # For non-power-of-two widths padding can select a fallback zero index.
        for width in (25,51,109):
            p=proof.prove_width(width)
            self.assertEqual(next(n['empty_index'] for n in p['nodes'] if n['index']==0),0)
            self.assertNotEqual(0,width-1)
            self.assertFalse(p['spare_status'].startswith('Known zero'))
        with self.assertRaises(ValueError):proof.prove_width(23)


if __name__=='__main__':unittest.main()
