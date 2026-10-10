"""Finite scalar DIV and SQRT IEEE reference, exact rationals/integer square root."""
from math import isqrt
import scalar_fpu_finite_oracle as finite


def sqrt_round(value,width,mode):
    if value<=0 or width not in (32,64) or mode not in ('rne','rup'):
        raise ValueError('Reviewed positive finite sqrt only')
    frac,bias=(23,127) if width==32 else (52,1023)
    e=value.numerator.bit_length()-value.denominator.bit_length()
    if value<finite.pow2(e):e-=1
    exponent=max(e//2,1-bias)
    square=value/finite.pow2(2*(exponent-frac))
    mant=isqrt(square.numerator//square.denominator)
    exact=mant*mant*square.denominator==square.numerator
    midpoint=(2*mant+1)**2*square.denominator
    if (mode=='rup' and not exact) or (mode=='rne' and
        (4*square.numerator>midpoint or (4*square.numerator==midpoint and mant&1))):mant+=1
    if mant>=1<<(frac+1):mant>>=1;exponent+=1
    encoded=exponent+bias if mant>=1<<frac else 0
    return (encoded<<frac)|(mant&((1<<frac)-1)),int(not exact)|(2 if not encoded and not exact else 0)


def evaluate(row):
    a=finite.decode(row['a'],row['width'])
    if row['operation']=='sqrt':return sqrt_round(a,row['width'],row['rounding'])
    if row['operation']!='div':raise ValueError('Unreviewed operation')
    b=finite.decode(row['b'],row['width'])
    if not a or not b:raise ValueError('Reviewed nonzero finite divide only')
    return finite.rounded(a/b,row['width'],row['rounding'])


def cases():
    rows=[]
    for width,frac,bias,ebits in ((32,23,127,8),(64,52,1023,11)):
        one=bias<<frac;half=(bias-1)<<frac;two=(bias+1)<<frac
        three=two|(1<<(frac-1));four=(bias+2)<<frac
        maximum=(((1<<ebits)-2)<<frac)|((1<<frac)-1)
        for name,op,a,b,rm in (
            ('exact_three','div',four|(1<<(frac-1)),two,'rne'),
            ('third_rne','div',one,three,'rne'),('third_rup','div',one,three,'rup'),
            ('exact_subnormal','div',1<<frac,two,'rne'),
            ('underflow','div',1,two,'rne'),('overflow','div',maximum,half,'rne'),
            ('sqrt_four','sqrt',four,0,'rne'),('sqrt_two_rne','sqrt',two,0,'rne'),
            ('sqrt_two_rup','sqrt',two,0,'rup'),('sqrt_min_normal','sqrt',1<<frac,0,'rne')):
            row=dict(index=len(rows),name=name,operation=op,width=width,a=a,b=b,c=0,rounding=rm)
            row['result'],row['flags']=evaluate(row);rows.append(row)
    return rows


def header(rows):return finite.header(rows)
