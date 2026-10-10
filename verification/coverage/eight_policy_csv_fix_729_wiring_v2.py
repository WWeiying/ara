"""Successor completing original catalog link pins from sealed729 endpoint identities."""
from pathlib import Path

import eight_policy_csv_fix_729_wiring as prior

SCRIPT=Path(__file__).resolve()
TEST=SCRIPT.with_name('test_eight_policy_csv_fix_729_wiring_v2.py')
frozen,require=prior.frozen,prior.require


class Context(prior.Context):
    def source_binding(self,pins):
        result=super().source_binding(pins)
        ledger=self.ledger();pairs={}
        # Frozen check_config requires both sides of every original catalog link.
        # A sealed endpoint proves bytes, not historical use of an unlisted alias.
        for link in frozen.INHERITED_TOOL_LINKS:
            identity=frozen.tool_link_identity(link)
            endpoint=identity['resolved']
            authority=link if link in ledger else endpoint
            expected=ledger.get(authority)
            require(expected==identity['sha256'],'Original catalog link lacks sealed729 endpoint authority')
            self.pin(pins,link,expected)
            require(pins.get(link)==pins.get(endpoint)==expected,'Original catalog link pair incomplete')
            pairs[link]=dict(identity,ledger_authority=authority,
                latest_ledger=str(self.admission/'evidence-pins.json'),
                latest_ledger_sha256=pins[str(self.admission/'evidence-pins.json')],
                historical_alias_invocation_claim=False)
        for path in (SCRIPT,TEST):self.pin(pins,path)
        result['original_catalog_endpoint_binding']=pairs
        result['actual_consumer_wiring'].update({str(p):frozen.sha(p) for p in (SCRIPT,TEST)})
        return result


# Only private function namespaces change; prior and every frozen file stay intact.
family=prior.private_module(prior,Context=Context,SCRIPT=SCRIPT,TEST=TEST)
read_six=family.read_six
six_backend=family.six_backend
eight_backend=family.eight_backend
fixed_backend=family.fixed_backend
runner_backend=family.runner_backend
prepare_six=family.prepare_six


if __name__=='__main__':family.main()
