"""Cache only a fully validated immutable completion, scoped to one active object."""
EXPECTED_READS = frozenset(range(1088))


def require(ok, message):
    if not ok:
        raise ValueError(message)


class CompletionCache:
    def __init__(self):
        self.active = None
        self.reads = None
        self.signature = None

    @staticmethod
    def state(active):
        return (active['ordinal'], active['returned'], active['tuple']['start'],
                active['preloads'], active['stores'], tuple(active['csrs']),
                active.get('entry_step'), active.get('target_pc'), active.get('target_step'))

    def finish(self, active):
        if active is None:
            return
        if active is self.active:
            require(active['reads'] is self.reads and
                    isinstance(active['csrs'], tuple) and
                    self.state(active) == self.signature,
                    'Completed call state changed')
            return
        require(active['returned'] and active['reads'] == EXPECTED_READS and
                tuple(active['csrs']) == (active['tuple']['start'], 0) and
                active['preloads'] == 2 and active['stores'] == 1,
                'Incomplete original1088/status/helper call ' + str(active['ordinal']))
        active['reads'] = frozenset(active['reads'])
        active['csrs'] = tuple(active['csrs'])
        self.active = active
        self.reads = active['reads']
        self.signature = self.state(active)


