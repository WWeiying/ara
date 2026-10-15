extern int macc_main(void);
extern void replay_text(const char *);
extern volatile unsigned long replay_case;
int main(void) { unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case=1;
replay_text("BOARD_CASE_BEGIN macc_e8_m4_pair480_481\n");
int result=macc_main();
if(result) { replay_text("BOARD_CASE_FAIL macc_e8_m4_pair480_481\n"); return result; }
replay_text("MACC_SELECTION_PASS macc_e8_m4_pair480_481 first=480 last=481 calls=2\nBOARD_CASE_PASS macc_e8_m4_pair480_481\nBOARD_REPLAY_PASS\n");
return 0;
}
