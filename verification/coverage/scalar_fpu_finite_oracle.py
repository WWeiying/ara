"""Finite IEEE binary32/64 ADD/MUL/FMA oracle using exact rational arithmetic."""
from fractions import Fraction


def pow2(e):
    return Fraction(1 << e) if e >= 0 else Fraction(1, 1 << -e)


def decode(bits, width):
    if width not in (32,64) or not 0 <= bits < 1 << width: raise ValueError('Invalid format/bits')
    frac, ebits = (23, 8) if width == 32 else (52, 11)
    sign, exp, mant = bits >> (width-1), (bits >> frac) & ((1 << ebits)-1), bits & ((1 << frac)-1)
    if exp == (1 << ebits)-1: raise ValueError('Finite inputs only')
    bias = (1 << (ebits-1))-1
    value = Fraction(mant + ((1 << frac) if exp else 0)) * pow2((exp or 1)-bias-frac)
    return -value if sign else value


def rounded(value, width, mode):
    if width not in (32,64): raise ValueError('Invalid format')
    if mode not in ('rne','rup'): raise ValueError('Unsupported reviewed rounding')
    frac, ebits = (23, 8) if width == 32 else (52, 11)
    bias = (1 << (ebits-1))-1; emin = 1-bias; emax = bias
    sign = int(value < 0); value = abs(value)
    if not value: return 0, 0
    exponent = value.numerator.bit_length()-value.denominator.bit_length()
    if value < pow2(exponent): exponent -= 1
    exponent = max(exponent, emin)
    scaled = value / pow2(exponent-frac)
    mant, rem = divmod(scaled.numerator, scaled.denominator)
    up = (2*rem > scaled.denominator or (2*rem == scaled.denominator and mant & 1)) if mode == 'rne' else (rem != 0 and not sign)
    mant += int(up)
    if mant >= 1 << (frac+1): mant >>= 1; exponent += 1
    if exponent > emax:
        inf = ((1 << ebits)-1) << frac
        magnitude = inf if mode == 'rne' or not sign else inf-1
        return (sign << (width-1)) | magnitude, 5
    encoded_exp = exponent+bias if mant >= 1 << frac else 0
    bits = (sign << (width-1)) | (encoded_exp << frac) | (mant & ((1 << frac)-1))
    flags = int(rem != 0)
    if not encoded_exp and flags: flags |= 2
    return bits, flags


def evaluate(case):
    a,b,c = (decode(case[k],case['width']) for k in ('a','b','c'))
    op = case['operation']
    if op == 'mul': value = a*b
    elif op == 'add': value = a+b
    elif op == 'fma': value = a*b+c
    else: raise ValueError('Unsupported operation')
    return rounded(value,case['width'],case['rounding'])


def cases():
    result = []
    for width,frac,bias,ebits in ((32,23,127,8),(64,52,1023,11)):
        one = bias << frac; sign = 1 << (width-1)
        half = (bias-1) << frac; two = (bias+1) << frac
        maximum = (((1 << ebits)-2) << frac) | ((1 << frac)-1)
        rows = [
            ('unfused_nx','mul',one+1,one-2,0,'rne'),
            ('fused_cancellation','fma',one+1,one-2,sign|one,'rne'),
            ('tie_even','add',one,(bias-frac-1)<<frac,0,'rne'),
            ('tie_up','add',one,(bias-frac-1)<<frac,0,'rup'),
            ('exact_subnormal','mul',1<<frac,half,0,'rne'),
            ('positive_underflow','mul',1,half,0,'rne'),
            ('negative_underflow','mul',sign|1,half,0,'rne'),
            ('overflow','mul',maximum,two,0,'rne'),
            ('fused_no_overflow','fma',maximum,two,sign|maximum,'rne'),
            ('exact_fourteen','fma',(bias+1)<<frac | (1<<(frac-1)),
                (bias+2)<<frac | (1<<(frac-2)),sign|one,'rne'),
        ]
        for name,op,a,b,c,rm in rows:
            case = dict(index=len(result),name=name,width=width,operation=op,a=a,b=b,c=c,rounding=rm)
            case['result'],case['flags'] = evaluate(case); result.append(case)
    return result


def header(rows):
    def operand(value,width): return value | (0xffffffff00000000 if width == 32 else 0)
    lines = ['struct sf_case { unsigned long a, b, c, result, flags; };',
             'const struct sf_case sf_cases[20] = {']
    for row in rows:
        vals = [operand(row[k],row['width']) for k in ('a','b','c')] + [row['result'],row['flags']]
        lines.append('  {'+', '.join('0x%016xul' % v for v in vals)+'},')
    return '\n'.join(lines+['};',''])
