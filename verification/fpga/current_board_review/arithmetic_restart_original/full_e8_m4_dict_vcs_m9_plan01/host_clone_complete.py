"""Complete mutable clone successor; old Host03 evidence remains immutable."""
import checker as c
import test_host as prior

def clone(value):
    result=prior.deepcopy(value)
    if isinstance(value,c.Strict):
        result.counts=list(value.counts)
        result.console=bytearray(value.console)
    return result
