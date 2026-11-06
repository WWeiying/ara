"""Extract the complete original fused RMSNorm group and one registered edit."""
import re
from audit import require

START='// fusion kinds that can be combined with the rms_norm computation in a single pass.\n'
END='static void ggml_compute_forward_rms_norm_back_f32(\n'
SUM='''                ggml_float sum = 0.0;
                // worth switching to explicit SIMD?
                for (int64_t i00 = 0; i00 < ne00; i00++) {
                    sum += (ggml_float)(x[i00] * x[i00]);
                }
'''
ORDERED='''                ggml_float sum = ggml_rvv_ordered_rms_sum(x, (size_t)ne00);
'''


def group(text):
    require(text.count(START)==text.count(END)==1,'Ambiguous RMSNorm source group')
    begin,end=text.index(START),text.index(END)
    require(begin<end,'RMSNorm group order')
    body=text[begin:end]
    require(body.count(SUM)==1 and body.count('void ggml_compute_forward_rms_norm_mul_fused(')==1,
            'Original fused reduction changed')
    return body


def shape_group(text):
    first='bool ggml_are_same_shape(const struct ggml_tensor * t0, const struct ggml_tensor * t1) {\n'
    last='bool ggml_are_same_stride(const struct ggml_tensor * t0, const struct ggml_tensor * t1) {\n'
    require(text.count(first)==text.count(last)==1,'Ambiguous shape helper')
    a,b=text.index(first),text.index(last);require(a<b,'Shape helper order')
    return '#include "ggml.h"\n'+text[a:b]


def translation_unit(text,candidate=False,prefix=None):
    body=group(text)
    if candidate:body=body.replace(SUM,ORDERED,1)
    prefix=prefix or ('candidate' if candidate else 'original')
    require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',prefix),'Invalid private symbol prefix')
    includes='''#include "ggml-cpu-impl.h"
#include "ops.h"
#include "vec.h"
#include <cmath>
'''
    if candidate:includes+='#include "rms_sum.h"\n'
    aliases=(f'#define ggml_compute_forward_rms_norm {prefix}_ggml_compute_forward_rms_norm\n'
             f'#define ggml_compute_forward_rms_norm_mul_fused {prefix}_ggml_compute_forward_rms_norm_mul_fused\n')
    wrapper='''
static void shape(ggml_tensor &t, const float *data, unsigned width, unsigned rows) {
    t.type=GGML_TYPE_F32; t.ne[0]=width; t.ne[1]=rows; t.ne[2]=t.ne[3]=1;
    t.nb[0]=sizeof(float); t.nb[1]=width*sizeof(float); t.nb[2]=t.nb[3]=rows*t.nb[1];
    t.data=const_cast<float *>(data);
}
extern "C" void PREFIX_rms_norm(const float *input, const float *weight,
                                unsigned width, unsigned rows, float eps, float *output) {
    ggml_tensor src{},w{},norm{},dst{};
    shape(src,input,width,rows);shape(w,weight,width,1);
    shape(norm,nullptr,width,rows);shape(dst,output,width,rows);
    norm.src[0]=&src;norm.op=GGML_OP_RMS_NORM;
    memcpy(norm.op_params,&eps,sizeof(eps));
    dst.src[0]=&norm;dst.src[1]=&w;dst.op=GGML_OP_MUL;
    ggml_compute_params params{};params.ith=0;params.nth=1;
    ggml_compute_forward_rms_norm_mul_fused(&params,&norm,&dst);
}
'''.replace('PREFIX',prefix)
    sum_wrapper=('\nextern "C" double PREFIX_rms_sum(const float *x, unsigned width) {\n'
                 '    const int64_t ne00=width;\n'+(ORDERED if candidate else SUM)+'    return sum;\n}\n')
    return aliases+includes+body+wrapper+sum_wrapper.replace('PREFIX',prefix)
