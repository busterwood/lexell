/* The instruction sequence the proposed SIMD extension would generate for a
   four-accumulator, 16-double dot-product loop (design/simd.md, "Exact
   lowering"), written by hand to measure it against the C ceiling.

   Three kernels differ only in how many of the four vector bounds checks the
   loop carries: 4 (the checks of the a and b loads merged by cse), 1 (a
   future facts pass proving the other three from the loop condition) and 8
   (no merge). The loads themselves are vmovupd from [base + i*8 + disp], the
   multiply-adds vfmadd231pd, and the reduction vextractf128/vaddpd/
   vunpckhpd/vaddsd, as x64gen would emit them. */
    .text
    .intel_syntax noprefix

.macro KERNEL name, nchecks
    .globl \name
    .type \name, @function
\name:
    vxorpd xmm8, xmm8, xmm8
    vxorpd xmm9, xmm9, xmm9
    vxorpd xmm10, xmm10, xmm10
    vxorpd xmm11, xmm11, xmm11
    xor eax, eax
    lea r8, [rdx - 15]          /* the loop condition i + 16 <= n, as i < n - 15 */
    lea r9, [rdx - 3]           /* the vector check i < n - 3 (i + 4 <= n) */
    cmp rax, r8
    jae 9f
1:
.if \nchecks >= 1
    cmp rax, r9
    jae 8f
.endif
.if \nchecks >= 2
    lea r10, [rax + 4]
    cmp r10, r9
    jae 8f
.endif
.if \nchecks >= 3
    lea r10, [rax + 8]
    cmp r10, r9
    jae 8f
.endif
.if \nchecks >= 4
    lea r10, [rax + 12]
    cmp r10, r9
    jae 8f
.endif
.if \nchecks >= 5
    cmp rax, r9
    jae 8f
.endif
.if \nchecks >= 6
    lea r10, [rax + 4]
    cmp r10, r9
    jae 8f
.endif
.if \nchecks >= 7
    lea r10, [rax + 8]
    cmp r10, r9
    jae 8f
.endif
.if \nchecks >= 8
    lea r10, [rax + 12]
    cmp r10, r9
    jae 8f
.endif
    vmovupd ymm0, [rdi + rax*8]
    vmovupd ymm1, [rdi + rax*8 + 32]
    vmovupd ymm2, [rdi + rax*8 + 64]
    vmovupd ymm3, [rdi + rax*8 + 96]
    vmovupd ymm4, [rsi + rax*8]
    vmovupd ymm5, [rsi + rax*8 + 32]
    vmovupd ymm6, [rsi + rax*8 + 64]
    vmovupd ymm7, [rsi + rax*8 + 96]
    vfmadd231pd ymm8, ymm0, ymm4
    vfmadd231pd ymm9, ymm1, ymm5
    vfmadd231pd ymm10, ymm2, ymm6
    vfmadd231pd ymm11, ymm3, ymm7
    add rax, 16
    cmp rax, r8
    jb 1b
9:
    vaddpd ymm8, ymm8, ymm9
    vaddpd ymm10, ymm10, ymm11
    vaddpd ymm8, ymm8, ymm10
    vextractf128 xmm0, ymm8, 1
    vaddpd ymm8, ymm8, ymm0
    vunpckhpd ymm1, ymm8, ymm8
    vaddsd xmm0, xmm8, xmm1
    /* the scalar tail, for the iterations after the vector loop */
10:
    cmp rax, rdx
    jae 11f
    vmovsd xmm1, [rdi + rax*8]
    vmulsd xmm1, xmm1, [rsi + rax*8]
    vaddsd xmm0, xmm0, xmm1
    inc rax
    jmp 10b
11:
    ret
8:
    ud2
    .size \name, .-\name
.endm

    KERNEL dot_lxl_check1, 1
    KERNEL dot_lxl_check4, 4
    KERNEL dot_lxl_check8, 8

    .section .note.GNU-stack,"",@progbits
