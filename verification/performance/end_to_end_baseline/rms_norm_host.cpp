#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

extern "C" void original_rms_norm(const float *,const float *,unsigned,unsigned,float,float *);
extern "C" [[noreturn]] void ggml_abort(const char *,int,const char *,...) {
    std::fputs("RMS_NORM_HOST_FAIL reason=upstream_assert\n",stderr);std::exit(1);
}
static void need(bool ok,const char *reason) {
    if (!ok) {std::fprintf(stderr,"RMS_NORM_HOST_FAIL reason=%s\n",reason);std::exit(1);}
}
static std::vector<float> load(const char *root,const char *name,size_t count) {
    char path[4096];need(std::snprintf(path,sizeof(path),"%s/%s",root,name)<int(sizeof(path)),"path");
    FILE *f=std::fopen(path,"rb");need(f,"open");std::vector<float> data(count);
    need(std::fread(data.data(),4,count,f)==count && std::fgetc(f)==EOF && !std::ferror(f),"length");
    need(std::fclose(f)==0,"close");return data;
}
int main(int argc,char **argv) {
    need(argc==2,"arguments");const auto input=load(argv[1],"input_f32.bin",4*2048);
    const auto weight=load(argv[1],"norm_weight_f32.bin",2048);
    const auto expected=load(argv[1],"expected_f32.bin",4*2048);
    const auto decode=load(argv[1],"decode_input_f32.bin",2048);
    const auto decode_expected=load(argv[1],"decode_expected_f32.bin",2048);
    const auto epsilon=load(argv[1],"epsilon.bin",1);std::vector<float> output(4*2048);
    original_rms_norm(input.data(),weight.data(),2048,4,epsilon[0],output.data());
    need(std::memcmp(output.data(),expected.data(),output.size()*4)==0,"captured_output_not_bitwise");
    for (float x:output)need(std::isfinite(x),"nonfinite");
    original_rms_norm(decode.data(),weight.data(),2048,1,epsilon[0],output.data());
    need(std::memcmp(output.data(),decode_expected.data(),2048*4)==0,"decode_output_not_bitwise");
    std::puts("RMS_NORM_REAL_DATA_PASS source=ggml_fused_rms_norm prefill_rows=4 decode_rows=1 width=2048 outputs=10240 bitwise=1");
}
