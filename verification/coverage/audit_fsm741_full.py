"""Full report audit using the unchanged qualified native checker."""
import audit_fsm741_exact as audit

if __name__ == '__main__':
    source = audit.life.OUT / 'fsm741-transition66-native-20261007-02/qualification.json'
    seal = '81d693efcb8b9be81152bbd77ed0ec761bc02d927c049037f11e86c454b7ea70'
    qualified = audit.life.read_bound(source, seal)
    audit.life.check(qualified['input_pins'])
    out = audit.life.OUT / 'fsm741-exact66-full-report-20261007-02'
    audit.audit(out)
    result = audit.life.read_bound(out / 'qualification.json', audit.life.digest(out / 'qualification.json'))
    audit.require(result['native_records'] == qualified['native_records'], 'Native import identities differ')
    audit.life.check(qualified['input_pins'])
    audit.life.save(out / 'native-import-binding.json', dict(source=str(source), source_seal=seal,
                    report_seal=audit.life.digest(out / 'qualification.json'), exact66_same_native=True))
