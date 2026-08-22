vmovupd (%rdi,%rdx,1),%zmm1
vfmadd213pd (%rax,%rdx,1),%zmm2,%zmm1
vmovupd %zmm1,(%rax,%rdx,1)
add $0x40,%rdx
cmp %rdx,%rsi
