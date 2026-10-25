"""Correct only the 45 packed-member selectors in the frozen fault profile."""
import copy

CUT = '/ara_tb/dut/i_ara_soc/i_system/i_ara/i_vlsu/i_axi_cut/'


def members():
    result = {}
    for prefix, req, rsp in (('up', 'slv_req_i', 'slv_resp_o'),
                             ('down', 'cut_req', 'cut_resp'),
                             ('bus', 'mst_req_o', 'mst_resp_i')):
        for name in ('ar_valid', 'r_ready'):
            result[prefix+'_'+name] = (req, name)
        for name in ('ar_ready', 'r_valid'):
            result[prefix+'_'+name] = (rsp, name)
        result[prefix+'_ar'] = (req, 'ar')
        for name in ('addr', 'id', 'len', 'size', 'burst'):
            result[prefix+'_ar_'+name] = (req, 'ar.'+name)
        for name in ('data', 'id', 'last', 'resp', 'user'):
            result[prefix+'_r_'+name] = (rsp, 'r.'+name)
    return result


def successor(original):
    if not isinstance(original, dict) or not isinstance(original.get('signals'), list):
        raise ValueError('Original fault profile required')
    if (original.get('clock'), original.get('edge'), original.get('raw_time_unit')) != (
            '/ara_tb/clk', 'negedge', '100fs'):
        raise ValueError('Original clock, sampling edge and time unit required')
    out = copy.deepcopy(original)
    entries = out['signals']
    if any(not isinstance(row, dict) or not isinstance(row.get('alias'), str) for row in entries):
        raise ValueError('Malformed signal entry')
    by_alias = {row['alias']: row for row in entries}
    if len(by_alias) != len(entries):
        raise ValueError('Duplicate signal alias')
    mapping = members()
    if len(mapping) != 45 or not set(mapping) <= set(by_alias):
        raise ValueError('Missing packed-member aliases')
    for alias, (root, member) in mapping.items():
        row = by_alias[alias]
        before = CUT+root+'/'+member.replace('.', '/')
        after = CUT+root+'.'+member
        if row.get('path') != before or row.get('format') != 'h' or row.get('required') is not True:
            raise ValueError('Changed member contract: '+alias)
        row['path'] = after
    # A second application must reject; no permissive global slash replacement.
    return out
