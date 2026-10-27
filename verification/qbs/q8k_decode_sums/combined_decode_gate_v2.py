"""Successor reporter: the nonexecuting fork parent emits no dispatch record."""
from combined_decode_gate import sources as original_sources,check_dispatch


def sources(before):
    original,wrapper=original_sources(before)
    marker='    const char *mode=getenv("GGML_QBS_COMBINED_TEST");\n'
    if wrapper.count(marker)!=1:raise ValueError('Reviewed reporter structure drift')
    wrapper=wrapper.replace(marker,marker+'    if(!mode && !old_calls && !new_calls) return;\n',1)
    return original,wrapper
