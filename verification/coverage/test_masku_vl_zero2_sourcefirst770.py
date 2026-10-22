import unittest
import masku_vl_zero2_sourcefirst770 as m


class ClosedRole(unittest.TestCase):
    def config(self):
        r=m.life.read_bound(m.source.REPORT,m.REVIEW_SHA)
        return dict(key=m.KEY,population=770,qualification_origin=m.ROLE,source_review_seal=m.REVIEW_SHA,
            binding_state='FRESH_COMPLETE_BEFORE_REQUIRED',local_qualified=False,qualification_seal=None,
            population_application=False,launch_authorized=False,ready_for_union=False,native_reference=None,
            native_targets=None,el=None,reference_pins={},candidate_bits=512,missing_serialized_positions=1024,
            prepared_overlap_positions=0,protected_children=r['protected_children'],instances=[dict(
                scope=m.source.SCOPE,toggle_checksum='1400516067',design_module_checksum='4132557224',
                compiled_parameters=r['compiled_parameters'],targets=[dict(n,native_label=None) for n in r['candidates']],
                protected=r['local_protected'])])

    def test_actual_source_config_contract(self):m.contract(self.config())

    def test_unknown_registry_or_receipt_promotion_rejected(self):
        for key,value in [('key','any_masku'),('local_qualified',True),('qualification_seal','fake'),
                          ('launch_authorized',True),('ready_for_union',True),('population_application',True),
                          ('native_reference',[]),('native_targets',[]),('el','Toggle guessed'),('reference_pins',{'fake':'fake'})]:
            c=self.config();c[key]=value
            with self.assertRaises(ValueError):m.contract(c)

    def test_guessed_label_or_port_target_rejected(self):
        for change in ('label','port','range'):
            c=self.config();n=c['instances'][0]['targets'][0]
            if change=='label':n['native_label']=n['name']+'[255:0]'
            elif change=='port':n['attributes']['portnode']='3'
            else:n['attributes']['left']='127'
            with self.assertRaises(ValueError):m.contract(c)

    def test_scope_move_or_checksum_rejected(self):
        for key,value in [('scope',m.source.SCOPE+'.child'),('toggle_checksum','1'),('design_module_checksum','1')]:
            c=self.config();c['instances'][0][key]=value
            with self.assertRaises(ValueError):m.contract(c)

    def test_missing_complement_arrays_child_or_output_rejected(self):
        for change in ('array','child','output'):
            c=self.config()
            if change=='child':c['protected_children'].pop()
            else:
                rows=c['instances'][0]['protected']
                index=next(i for i,n in enumerate(rows) if
                    (n['kind']=='arrays' if change=='array' else n['name']=='bit_enable_mask_o'))
                rows.pop(index)
            with self.assertRaises(ValueError):m.contract(c)


if __name__=='__main__':unittest.main()
