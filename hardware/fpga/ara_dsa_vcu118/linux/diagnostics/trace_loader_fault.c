/* No libc/RVV in the observer. The child executes the original dynamic cat.
 * No breakpoints, register writes, or memory writes into the traced process.
 * A real fault stays ptrace-stopped; reboot/termination is deliberately manual.
 */
typedef unsigned long word;
void *memset(void *dst,int value,word n) {
  unsigned char *d=dst;
  for(word i=0;i<n;++i) d[i]=(unsigned char)value;
  return dst;
}
void *memcpy(void *dst,const void *src,word n) {
  unsigned char *d=dst; const unsigned char *s=src;
  for(word i=0;i<n;++i) d[i]=s[i];
  return dst;
}
struct iovec { void *base; word length; };
static long sc(long n, long x, long y, long z, long w) {
  register long a0 __asm__("a0") = x;
  register long a1 __asm__("a1") = y;
  register long a2 __asm__("a2") = z;
  register long a3 __asm__("a3") = w;
  register long a7 __asm__("a7") = n;
  __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a7) : "memory");
  return a0;
}
static void text(const char *s) {
  word n=0;
  while (s[n]) ++n;
  while (n) {
    long r=sc(64,1,(long)s,n,0);
    if (r<=0) return;
    s+=r; n-=r;
  }
}
static void hex(word v) {
  char s[19]="0x0000000000000000";
  const char *digits="0123456789abcdef";
  for (int i=17;i>=2;--i) { s[i]=digits[v&15]; v>>=4; }
  text(s);
}
static void field(const char *name, word v) { text(name); text("="); hex(v); text("\n"); }
static int equal(const char *a,const char *b) {
  while (*a && *a==*b) { ++a; ++b; }
  return *a==*b;
}
static void proc_path(char *s,long pid,const char *file) {
  const char *prefix="/proc/";
  while (*prefix) *s++=*prefix++;
  char digits[24]; int n=0;
  do { digits[n++]=(char)('0'+pid%10); pid/=10; } while(pid);
  while(n) *s++=digits[--n];
  *s++='/';
  while (*file) *s++=*file++;
  *s=0;
}
static void dump_maps(long pid) {
  char path[64],buf[512];
  proc_path(path,pid,"maps");
  long fd=sc(56,-100,(long)path,0,0);
  field("maps_open",fd);
  if(fd<0) return;
  for(int i=0;i<32;++i) {
    long n=sc(63,fd,(long)buf,sizeof(buf)-1,0);
    if(n<=0) break;
    buf[n]=0; text(buf);
  }
  sc(57,fd,0,0,0);
}
static void peek(long pid,word addr) {
  word v=0;
  long r=sc(117,2,pid,addr,(long)&v);
  text("PEEK "); hex(addr); text(" ret="); hex(r); text(" data="); hex(v); text("\n");
}
static void pagemap(long pid,word va) {
  char path[64]; word entry=0;
  proc_path(path,pid,"pagemap");
  long fd=sc(56,-100,(long)path,0,0);
  if(fd<0) { field("pagemap_open",fd); return; }
  long pos=sc(62,fd,(va>>12)*8,0,0);
  long n=pos<0 ? pos : sc(63,fd,(long)&entry,8,0);
  text("PAGEMAP "); hex(va); text(" ret="); hex(n); text(" entry="); hex(entry); text("\n");
  sc(57,fd,0,0,0);
}
static long regs(long pid,word *r) {
  struct iovec io={r,32*sizeof(word)};
  long ret=sc(117,0x4204,pid,1,(long)&io);
  return ret ? ret : (io.length==32*sizeof(word) ? 0 : -1);
}
__attribute__((noreturn)) static void hold(void) {
  word delay[2]={1,0};
  for(;;) sc(101,(long)delay,0,0,0);
}
__attribute__((noreturn)) static void finish(long code) {
  sc(94,code,0,0,0);
  for(;;) {}
}
static void fault(long pid, int status, word loader, word initial_sp, word *r) {
  text("TRACE_FAULT\n"); field("pid",pid);
  field("wait_status",status); field("loader_base",loader); field("initial_sp",initial_sp);
  for(int i=0;i<32;++i) { text("REG "); hex(i); text(" "); hex(r[i]); text("\n"); }
  if(loader) {
    for(int k=0;k<2;++k) {
      field("peek_round",k);
      for(int i=0;i<8;++i) peek(pid,loader+0x22c90+8*i);
      peek(pid,loader+0x24238);
      pagemap(pid,loader+0x22cb8);
      pagemap(pid,loader+0x24238);
    }
  }
  for(int i=0;i<16;++i) peek(pid,initial_sp+8*i);
  pagemap(pid,initial_sp);
  for(int i=0;i<8;++i) peek(pid,(r[10]&~31UL)+8*i);
  peek(pid,r[0]&~7UL);
  dump_maps(pid);
}
/* Follow the real shell's fork/vfork/exec chain, not a replacement cat loop.
 * Only event stops occur before a fault; no prefetches or instruction stepping.
 */
__attribute__((noreturn)) static void command_trace(char *command,char **env) {
  struct child { long pid; word base,sp; } children[64]={0};
  long root=sc(220,17,0,0,0);
  if(root<0) finish(2);
  if(!root) {
    if(sc(117,0,0,0,0)<0) finish(120);
    sc(129,sc(172,0,0,0,0),19,0,0);
    char *args[]={"sh","-c",command,0};
    sc(221,(long)"/bin/sh",(long)args,(long)env,0);
    finish(121);
  }
  int status=0,live=1,failed=0,execs=0;
  if(sc(260,root,(long)&status,0,0)!=root || status!=0x137f) finish(3);
  children[0].pid=root;
  if(sc(117,0x4200,root,0,2|4|8|16)<0 || sc(117,7,root,0,0)<0) finish(4);
  text("TRACE_TREE_BEGIN\n");
  while(live) {
    long pid=sc(260,-1,(long)&status,0x40000000,0);
    if(pid<0) { field("wait_error",pid); hold(); }
    int slot=-1;
    for(int i=0;i<64;++i) if(children[i].pid==pid) slot=i;
    if(slot<0) {
      for(int i=0;i<64;++i) if(!children[i].pid) { slot=i; break; }
      if(slot<0) { text("TRACE_TREE_FULL\n"); hold(); }
      children[slot]=(struct child){pid,0,0}; ++live;
    }
    if((status&255)!=127) {
      if(status) { field("child_status",status); failed=1; }
      children[slot].pid=0; --live; continue;
    }
    int event=status>>16,sig=(status>>8)&255;
    if(event>=1 && event<=3) {
      word child=0;
      if(sc(117,0x4201,pid,0,(long)&child)<0) finish(4);
      field("fork_child",child);
    } else if(event==4) {
      word r[32];
      if(regs(pid,r)<0) finish(5);
      children[slot].sp=r[2];
      children[slot].base=(r[0]&4095)==0xe84 ? r[0]-0x10e84 : 0;
      ++execs;
      if(execs%25==0) field("execs",execs);
    } else if(sig!=19 && sig!=17) {
      word r[32];
      if(regs(pid,r)<0) finish(5);
      fault(pid,status,children[slot].base,children[slot].sp,r);
      text("TRACE_HOLDING child_stopped observer_alive\n"); hold();
    }
    if(sc(117,7,pid,0,(!event && sig==17)?17:0)<0) finish(6);
  }
  field("execs",execs);
  text(failed?"TRACE_TREE_FAILED\n":"TRACE_PASS\n"); finish(failed);
}
__attribute__((used,noreturn)) void run(word *stack) {
  long argc=stack[0]; char **argv=(char **)(stack+1);
  char **env=argv+argc+1;
  if(argc==3 && equal(argv[1],"--command")) command_trace(argv[2],env);
  if(argc>1 && equal(argv[1],"--fault")) {
    __asm__ volatile("ld zero,0(zero)" ::: "memory");
    finish(99);
  }
  int selftest=argc>1 && equal(argv[1],"--selftest");
  int rounds=200;
  if(argc>1 && !selftest) {
    rounds=0;
    for(char *p=argv[1];*p;++p) {
      if(*p<'0' || *p>'9' || rounds>1000) finish(2);
      rounds=rounds*10+*p-'0';
    }
    if(rounds<1 || rounds>1000) finish(2);
  }
  if(selftest) rounds=1;
  text("TRACE_BEGIN no_breakpoints original_child retained_on_fault\n");
  for(int iteration=0;iteration<rounds;++iteration) {
    long pid=sc(220,17,0,0,0);
    if(pid<0) { field("clone_error",pid); finish(2); }
    if(!pid) {
      if(sc(117,0,0,0,0)<0) finish(120);
      sc(129,sc(172,0,0,0,0),19,0,0);
      char *cat[]={"cat","/tmp/ara_loader_probe_input",0};
      char *test[]={argv[0],"--fault",0};
      sc(221,(long)(selftest?argv[0]:"/bin/cat"),(long)(selftest?test:cat),(long)env,0);
      finish(121);
    }
    int status=0;
    if(sc(260,pid,(long)&status,0,0)!=pid || status!=0x137f) finish(3);
    // TRACEEXEC produces one stop before user loader code. No memory read here:
    // prefetching its globals would change the demand-fault behavior under test.
    if(sc(117,0x4200,pid,0,16)<0) finish(4);
    word loader=0,initial_sp=0; int saw_exec=0;
    for(;;) {
      if(sc(117,7,pid,0,0)<0) finish(5);
      if(sc(260,pid,(long)&status,0,0)!=pid) finish(6);
      if(!(status&127)) {
        if((status>>8)!=0 || !saw_exec) { field("child_exit",status); finish(7); }
        break;
      }
      word r[32];
      if((status&255)!=127 || regs(pid,r)<0) { field("bad_stop",status); hold(); }
      if((status>>16)==4) {
        saw_exec=1; initial_sp=r[2];
        if(!selftest && (r[0]&4095)==0xe84) loader=r[0]-0x10e84;
        else if(!selftest) { field("unexpected_entry",r[0]); hold(); }
        continue;
      }
      text("TRACE_FAULT\n"); field("iteration",iteration); field("pid",pid);
      field("wait_status",status); field("loader_base",loader); field("initial_sp",initial_sp);
      for(int i=0;i<32;++i) { text("REG "); hex(i); text(" "); hex(r[i]); text("\n"); }
      // Repeated reads distinguish observed state from a single failed peek.
      if(loader) {
        for(int k=0;k<2;++k) {
          field("peek_round",k);
          for(int i=0;i<4;++i) peek(pid,loader+0x22ca0+8*i);
          pagemap(pid,loader+0x22cb8);
        }
        for(int i=0;i<4;++i) peek(pid,initial_sp+8*i);
      }
      peek(pid,r[0]&~7UL);
      dump_maps(pid);
      if(selftest && ((status>>8)&255)==11) {
        sc(117,8,pid,0,0); sc(260,pid,(long)&status,0,0);
        text("TRACE_SELFTEST_OK\n"); finish(0);
      }
      text("TRACE_HOLDING child_stopped observer_alive\n"); hold();
    }
    if(iteration%10==0) field("completed",iteration+1);
  }
  text("TRACE_PASS\n"); finish(0);
}
__asm__(".global _start\n_start:\nmv a0,sp\ncall run\nunimp\n");
