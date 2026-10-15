"""Narrow metadata successor tests; do not repeat sealed full144 Host/reference."""
import copy
import replay02 as s

def main():
    a=s.base.read(s.ADDENDUM); original=s.base.read(s.base.SOURCE_REVIEW/'REVIEW.json')
    passed=[]
    def reject(label,mutate):
        bad=copy.deepcopy(a); mutate(bad)
        try:s.effective_binding(original,bad)
        except (ValueError,KeyError):passed.append(label);return
        raise AssertionError('Accepted '+label)
    pins=s.source_review02()
    reject('unapproved_document_digest',lambda x:x['superseded_pins'][0].__setitem__('new_sha256','0'*64))
    reject('drop_source_pin',lambda x:x['effective_hashes'].pop(str(s.base.REF/'READY.json')))
    reject('change_source_pin',lambda x:x['effective_hashes'].__setitem__(str(s.base.REF/'READY.json'),'0'*64))
    reject('add_second_supersession',lambda x:x['superseded_pins'].append(dict(x['superseded_pins'][0])))
    reject('pretend_worker_review',lambda x:x.__setitem__('worker_entry_reviewed',True))
    reject('pretend_DUT_authorized',lambda x:x.__setitem__('DUT_authorized_by_this_review',True))
    # The actual prior Host belongs to unchanged runtime/checker files.
    host=s.base.read(s.base.HERE/'host02.json'); s.base.verify(host['pins'])
    s.base.require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['cases']==144,'Sealed Host unchanged')
    result=dict(status='PASS_METADATA_SUCCESSOR_ONLY_NOT_DUT',positive=1,negative=len(passed),negative_names=passed,
                inherited_host_sha256=s.base.sha(s.base.HERE/'host02.json'),actual_review_pins=pins,
                pins={str(s.base.HERE/name):s.base.sha(s.base.HERE/name) for name in ('replay02.py','test_binding02.py')})
    s.base.save(s.base.HERE/'binding_host02.json',result)
    print(result['status'],len(passed))

if __name__=='__main__':main()
