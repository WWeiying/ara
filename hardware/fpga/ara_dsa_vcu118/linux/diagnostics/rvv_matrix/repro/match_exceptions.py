"""Parse individual trap records without mixing registers across children."""
import re


def fault_records(output):
    starts = list(re.finditer(r'\bunhandled signal (\d+) code ', output))
    result = []
    for index, start in enumerate(starts):
        block = output[start.start():starts[index+1].start() if index+1<len(starts) else len(output)]
        patterns = dict(epc=r'\bepc\s*:\s*([0-9a-f]+)',
                        address=r'\ba0\s*:\s*([0-9a-f]+)',
                        tval=r'\bbadaddr:\s*([0-9a-f]+)',
                        cause=r'\bcause:\s*([0-9a-f]+)')
        fields = {key:re.findall(pattern, block) for key,pattern in patterns.items()}
        # Rate-limited/truncated kernel messages are not complete trap evidence.
        if any(len(values)!=1 for values in fields.values()):
            continue
        row = {key:int(values[0],16) for key,values in fields.items()}
        row.update(signal=int(start[1]), output=block)
        row['offset'] = row['tval']-row['address']
        result.append(row)
    return result


def scenario_counts(result, scenario):
    pattern = (rf'^RVV_EXCEPTION_SCENARIO id={scenario} unexpected_signals=(\d+) '
               r'nonzero_exits=(\d+) wait_failures=(\d+)$')
    found = re.findall(pattern, result['output'], re.MULTILINE)
    if len(found)!=1:
        raise ValueError('Missing or ambiguous scenario counters')
    if result['status']!='failed' or result['exit_code']!=1:
        raise ValueError('Parent did not report architectural failure')
    return tuple(map(int,found[0]))


def candidates(result, scenario, sew):
    offset = 0 if scenario in (3,5) else 4*(sew//8)
    return [r for r in fault_records(result['output']) if
            r['signal']==11 and r['cause']==13 and r['offset']==offset]
