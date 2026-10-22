extern int arithmetic_main(void);
extern void replay_text(const char *);
extern volatile unsigned long replay_case;
int main(void) { unsigned long vlenb;
__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
replay_case=1;
replay_text("BOARD_CASE_BEGIN arithmetic_e8_m2_prefix56\n");
int result=arithmetic_main();
if(result) { replay_text("BOARD_CASE_FAIL arithmetic_e8_m2_prefix56\n"); return result; }
replay_text("ARITHMETIC_PREFIX_PASS arithmetic_e8_m2_prefix56 trials=56\nBOARD_CASE_PASS arithmetic_e8_m2_prefix56\nBOARD_REPLAY_PASS\n");
return 0;
}
