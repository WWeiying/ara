"""Ordered SoftFloat successor. Target libm values enter only through exact samples."""
from fractions import Fraction
import hashlib
import importlib.util
import struct

NEG_INF = 0xff800000
ONE = 0x3f800000
SCALE = 1035273459


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def number(value):
    return struct.unpack('<f', struct.pack('<I', value))[0]


def unpack(raw, width):
    return list(struct.unpack('<'+{16:'H',32:'I'}[width]*(len(raw)//(width//8)), raw))


def features(**changes):
    result = dict(softcap=0, mask_scale_enabled=0, position_bias_enabled=1,
        sinks_enabled=1, window_enabled=1, mask_scale=[ONE,ONE],
        position_slope=[bits(2**-7),bits(2**-6)], sinks=[bits(-2),bits(-1)],
        key_position_base=4096, query_position=4232, window_left=100, window_right=0)
    result.update(changes)
    return result


PERFORMANCE = dict(name='real_qwen3_derived_features', dimension=128, heads=2,
    tokens=137, capacity=256, features=features(), mask_override=[])
FUNCTIONAL = dict(name='derived_d64_t5_softcap', dimension=64, heads=2,
    tokens=5, capacity=256, features=features(softcap=bits(2), query_position=4098,
        window_left=2, window_right=2, mask_scale_enabled=1,
        mask_scale=[ONE,bits(2)], position_slope=[bits(.125),bits(-.0625)],
        sinks=[bits(2),bits(.5)]), mask_override=[[1,0xfc00],[3,0x3800]])
EXCLUDED = dict(name='derived_d64_t1_excluded_no_sink', dimension=64, heads=2,
    tokens=1, capacity=256, features=features(sinks_enabled=0, window_left=0), mask_override=[])
EXCLUDED_SINK = dict(name='derived_d64_t1_excluded_sink', dimension=64, heads=2,
    tokens=1, capacity=256, features=features(window_left=0), mask_override=[])
TAILS = tuple(dict(name='derived_t65_'+order+'_sink'+str(sink), dimension=64, heads=2,
    tokens=65, capacity=256, mask_override=[], features=features(sinks_enabled=sink,
        query_position=4160 if order == 'excluded_first' else 4159,
        window_left=0 if order == 'excluded_first' else 63))
    for order in ('excluded_first','excluded_tail') for sink in (0,1))
GROUPED = dict(name='derived_two_groups_h3', dimension=64, heads=6, rows=3,
    tokens=5, capacity=256, query_rows=[0,1,0,1,0,1], mask_override=[], features=[
        features(query_position=4100,mask_scale=[ONE]*3,
            position_slope=[bits(-.03125),bits(.03125),bits(.09375)],
            sinks=[bits(-2),bits(-1),0]),
        features(query_position=4100,mask_scale=[ONE]*3,
            position_slope=[bits(.0625),bits(-.0625),bits(.125)],
            sinks=[bits(.5),bits(1.5),bits(2.5)])])
CASES = (PERFORMANCE, FUNCTIONAL, EXCLUDED, EXCLUDED_SINK, *TAILS, GROUPED)


def local_features(case, head):
    f = case['features']
    if isinstance(f,list):
        return f[head//case['rows']],head%case['rows']
    return f,head


def directed():
    f = features(softcap=bits(2), query_position=4098, window_left=2, window_right=2,
                 mask_scale_enabled=1, mask_scale=[ONE,bits(2)])
    rows = [dict(name=name, dot=bits(2), scale=bits(.5), mask=0x3800,
                 head=head, index=index, features=f)
            for name,head,index in (('left_inclusive',0,0),('right_inclusive',1,4),
                                    ('right_excluded',1,5),('local_head1',1,2))]
    excluded = features(softcap=1, mask_scale_enabled=1,
                        mask_scale=[0x7f7fffff]*2, position_slope=[0x7f7fffff]*2)
    for name,dot,scale,mask in (('mask_before_scale',0x7f7fffff,0x7f7fffff,0xfc00),
                              ('window_after_scale',0x7f7fffff,0x7f7fffff,0x7bff),
                              ('window_before_later_ops',ONE,ONE,0x7bff)):
        rows.append(dict(name=name,dot=dot,scale=scale,mask=mask,head=0,index=0,features=excluded))
    return rows


class Context:
    def __init__(self, root):
        self.base = load(root/'verification/performance/resident_rvv/qk_shared/full_call_sdk/flags_v2/fixture.py',
                         'stage4_ordered_foundation')
        self.oracle = load(root/'verification/fpnew_upstream_20261009/oracle.py', 'stage4_softfloat')


class Arithmetic:
    def __init__(self, ctx, samples=None):
        self.ctx, self.sf = ctx, ctx.oracle.SoftFloat()
        self.flags, self.phase, self.phase_flags = 0, None, {}
        self.reduction_checks = 0
        self.samples = samples or {}
        self.used = set()

    def op(self, op, width, a, b=0, c=0, dst=None, unsigned=False):
        value, flags = self.sf.evaluate(op,width,dst or width,0,a,b,c,unsigned)
        self.raise_flags(flags)
        return value

    def raise_flags(self, flags):
        self.flags |= flags
        if self.phase is not None:
            self.phase_flags[self.phase] = self.phase_flags.get(self.phase,0) | flags

    def cast(self, src, dst, value):
        return self.op('cast',src,value,dst=dst)

    def add(self, width, a, b):
        return self.op('fma',width,{32:ONE,64:0x3ff0000000000000}[width],a,b)

    def sub(self, a, b):
        return self.add(32,a,b ^ 0x80000000)

    def libm(self, name, value):
        key = (name,value)
        require(key in self.samples, 'Missing target libm sample: '+str(key))
        output, flags = self.samples[key]
        self.used.add(key)
        self.raise_flags(flags)
        return output

    def vector_exp(self, value):
        return self.ctx.base.Arithmetic.vector_exp(self,value)

    def sum_scores(self, scores, scaled_sum):
        values = [Fraction.from_float(number(x)) for x in [*scores,scaled_sum]]
        total = sum(values,Fraction())
        require(all(x >= 0 for x in values) and total > 0, 'Invalid softmax sum')
        def rounded(value):
            raw = struct.unpack('<Q',struct.pack('<d',float(value)))[0]
            return self.sf.evaluate('cast',64,32,0,raw)[0]
        # Positive subset sums cannot exceed this common-grid integer total.
        # At <=53 bits every F64 tree is exact, including an F32 halfway result.
        denominator = max(x.denominator for x in values)
        units = sum(x.numerator*(denominator//x.denominator) for x in values)
        exact_tree = units.bit_length() <= 53
        error = 0 if exact_tree else total*Fraction(2*(len(values)+1),1 << 52)
        require(rounded(total-error) == rounded(total+error), 'F64 tree changes F32 result')
        require(exact_tree or self.flags & 1, 'Reduction NX needs independent tree analysis')
        value = 0
        for score in scores:
            value = self.add(64,value,self.cast(32,64,score))
        value = self.add(64,value,self.cast(32,64,scaled_sum))
        result = self.cast(64,32,value)
        require(result == rounded(total), 'Reduction proof disagreement')
        self.reduction_checks += 1
        return result


def transform(a, dot, scale, mask, head, index, f, tanh_requests=None):
    if mask == 0xfc00:
        return NEG_INF
    value = a.op('mul',32,dot,scale)
    position = f['key_position_base']+index
    if f['window_enabled'] and ((position < f['query_position'] and
        f['query_position']-position > f['window_left']) or (position > f['query_position'] and
        position-f['query_position'] > f['window_right'])):
        return NEG_INF
    if f['softcap']:
        argument = a.op('div',32,value,f['softcap'])
        if tanh_requests is not None:
            tanh_requests.add(('tanhf',argument))
            return None  # Discovery only: never treat a missing tanh result as a score.
        value = a.op('mul',32,f['softcap'],a.libm('tanhf',argument))
    if f['position_bias_enabled']:
        distance = a.op('i2f',64,abs(position-f['query_position']),dst=32,unsigned=True)
        if position < f['query_position']:
            distance ^= 0x80000000
        value = a.add(32,value,a.op('mul',32,f['position_slope'][head],distance))
    bias = a.op('mul',32,a.cast(16,32,mask),f['mask_scale'][head] if f['mask_scale_enabled'] else ONE)
    return a.add(32,value,bias)


def dot_rows(ctx, data, case):
    a = Arithmetic(ctx)
    source, k16 = unpack(data['query_f16'],16), unpack(data['key'],16)
    d = case['dimension']
    query_rows = case.get('query_rows',[0,1])
    q16 = [[source[h*128+j] for j in range(d)] for h in query_rows]
    rows = []
    for h in range(case['heads']):
        row = []
        for t in range(case['tokens']):
            a.phase = ('QK',h,t//64*64)
            dot = 0
            for j in range(d):
                dot = a.op('fma',32,a.cast(16,32,q16[h][j]),a.cast(16,32,k16[t*128+j]),dot)
            row.append(dot)
        rows.append(row)
    return rows,a.flags,a.phase_flags


def prepare_scores(ctx, data, case, dots, samples=None, discover=False):
    a, requests, scores = Arithmetic(ctx,samples),set(),[]
    masks = unpack(data['mask'],16)
    for h in range(case['heads']):
        f,local = local_features(case,h)
        scores.append([transform(a,dot,SCALE,dict(case['mask_override']).get(t,masks[t]),local,t,
                                f,requests if discover else None)
                       for t,dot in enumerate(dots[h])])
    return scores,a.flags,requests,a.used


def alpha_requests(scores, case):
    result, maxima = set(),[]
    for h,row in enumerate(scores):
        f,local = local_features(case,h)
        maximum = f['sinks'][local] if f['sinks_enabled'] else NEG_INF
        for start in range(0,len(row),64):
            updated = max([maximum,*row[start:start+64]],key=number)
            if maximum != NEG_INF:
                # Both values are finite target F32; use SoftFloat at the caller.
                result.add((maximum,updated))
            maxima.append(dict(head=h,tile=start,old=maximum,new=updated))
            maximum = updated
    return result,maxima


def expected(ctx, data, case, dots, qk_flags, qk_phases, samples):
    scores,transform_flags,_,used = prepare_scores(ctx,data,case,dots,samples)
    a = Arithmetic(ctx,samples)
    a.flags = qk_flags | transform_flags
    a.used |= used
    a.phase_flags.update(qk_phases)
    value, outputs, maxima = unpack(data['value'],16),[],[]
    d = case['dimension']
    for h in range(case['heads']):
        f,local = local_features(case,h)
        acc = [0]*d
        maximum = f['sinks'][local] if f['sinks_enabled'] else NEG_INF
        total = ONE if f['sinks_enabled'] else 0
        for start in range(0,case['tokens'],64):
            row = scores[h][start:start+64]
            updated = max([maximum,*row],key=number)
            maxima.append(dict(head=h,tile=start,old=maximum,new=updated))
            if updated == NEG_INF:
                alpha, probabilities = 0,[0]*len(row)
            else:
                alpha = 0 if maximum == NEG_INF else a.libm('expf',a.sub(maximum,updated))
                probabilities = [a.vector_exp(a.sub(x,updated)) for x in row]
                total = a.sum_scores(probabilities,a.op('mul',32,total,alpha))
                maximum = updated
            a.phase = ('PV_PREP',h,start)
            half_alpha = a.cast(32,16,alpha)
            acc = [a.op('mul',16,x,half_alpha) for x in acc]
            coefficients = [a.cast(32,16,x) for x in probabilities]
            a.phase = ('PV',h,start)
            for t,coefficient in enumerate(coefficients,start):
                for j in range(d):
                    acc[j] = a.op('fma',16,coefficient,value[t*128+j],acc[j])
            a.phase = None
        inverse = a.op('div',32,ONE,total) if total else 0
        outputs += [a.op('mul',32,a.cast(16,32,x),inverse) for x in acc]
    return dict(bits=outputs, output_sha256=hashlib.sha256(struct.pack('<'+'I'*len(outputs),*outputs)).hexdigest(),
        fflags=a.flags,maxima=maxima,reduction_checks=a.reduction_checks,
        phases=[dict(phase=list(k),fflags=v) for k,v in a.phase_flags.items()]),a.used


def sample_table(requests, records):
    require(isinstance(records,list) and len(records) == len(requests),'Sample count mismatch')
    table = {}
    for row in records:
        require(isinstance(row,dict) and set(row) == {'function','input','output','fflags'},'Sample fields')
        require(row['function'] in ('expf','tanhf') and
                all(type(row[k]) is int and 0 <= row[k] <= 0xffffffff for k in ('input','output')) and
                type(row['fflags']) is int and 0 <= row['fflags'] <= 31,'Sample values')
        key = (row['function'],row['input'])
        require(key not in table,'Duplicate sample')
        table[key] = (row['output'],row['fflags'])
    require(set(table) == set(requests),'Missing/extra sample')
    return table
