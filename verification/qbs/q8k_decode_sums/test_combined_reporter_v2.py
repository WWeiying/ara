"""Exercise destructor/fork behavior directly, without running a model."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from combined_decode_gate_v2 import sources,check_dispatch


HARNESS=r'''
#include <sys/wait.h>
#include <unistd.h>
void decode_original(const float *x,void *y,int64_t k) {(void)k;*(float *)y=*x;}
void __real_quantize_row_q8_K(const float *x,void *y,int64_t k) {(void)k;*(float *)y=*x;}
int main(int argc,char **argv) {
    (void)argv;
    if(argc>1) {
        setenv("GGML_QBS_COMBINED_TEST","1",1);
        float x=1,y=0;__wrap_quantize_row_q8_K(&x,&y,1);
        unsetenv("GGML_QBS_COMBINED_TEST");
        return 0;
    }
    unsetenv("GGML_QBS_COMBINED_TEST");
    for(int m=0;m<2;++m) {
        pid_t child=fork();if(child<0)return 1;
        if(!child) {
            setenv("GGML_QBS_COMBINED_TEST",m ? "1":"0",1);
            float x=1,y=0;__wrap_quantize_row_q8_K(&x,&y,1);
            exit(y==1 ? 0:2);
        }
        int status;
        if(waitpid(child,&status,0)!=child||!WIFEXITED(status)||WEXITSTATUS(status))return 3;
    }
    return 0;
}
'''


class ReporterTest(unittest.TestCase):
    def test_parent_silence_and_nonzero_parent_not_hidden(self):
        before='void quantize_row_q8_K(const float *x,void *y,int64_t k) {}\n//===================================== Dot products\n'
        _,wrapper=sources(before)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'report.c';source.write_text(wrapper+HARNESS)
            subprocess.run(['gcc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(root/'test')],
                           check=True,capture_output=True,text=True,timeout=30)
            result=subprocess.run([str(root/'test')],check=True,capture_output=True,text=True,timeout=10)
            activity={str(m):dict(groups=[dict(m=1,calls=1)]) for m in (0,1)}
            self.assertEqual(len(check_dispatch(result.stdout,activity)),2)
            self.assertNotIn('invalid',result.stdout)
            result=subprocess.run([str(root/'test'),'nonzero-parent'],check=True,
                                  capture_output=True,text=True,timeout=10)
            self.assertEqual(result.stdout.strip(),'Q8K_COMBINED_DISPATCH mode=invalid original=0 installed=1')
            with self.assertRaises(ValueError):check_dispatch(result.stdout,activity)


if __name__=='__main__':unittest.main()
