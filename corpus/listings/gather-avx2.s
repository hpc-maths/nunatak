vmovdqu (%rsi),%xmm2
vmovapd %ymm3,%ymm4
add $0x10,%rsi
vgatherdpd %ymm4,(%rdi,%xmm2,8),%ymm0
vaddpd %ymm0,%ymm1,%ymm1
cmp %rax,%rsi
