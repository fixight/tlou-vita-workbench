
FUNCTION 0x811160
00811160: push rbp
00811161: mov rbp, rsp
00811164: push r15
00811166: push r14
00811168: push r13
0081116a: push r12
0081116c: push rbx
0081116d: push rax
0081116e: mov r12, rdi
00811171: mov edi, 0xe1a8c886
00811176: and byte ptr [r12 + 0xe], 0xf7
0081117c: mov rdx, qword ptr [r12 + 0x40]
00811181: movsx esi, word ptr [r12 + 0x30]
00811187: call 0x7ae390
0081118c: mov r14, rax
0081118f: test r14, r14
00811192: je 0x81120c
00811194: mov ax, word ptr [r12 + 0x30]
0081119a: xor r13d, r13d
0081119d: mov ebx, 8
008111a2: test ax, ax
008111a5: jle 0x8111f8
008111a7: xor r15d, r15d
008111aa: nop word ptr [rax + rax]
008111b0: mov rcx, qword ptr [r12 + 0x40]
008111b5: cmp dword ptr [rcx + rbx - 8], 0x3da64e6a
008111bd: jne 0x8111df
008111bf: mov esi, dword ptr [r14 + 8]
008111c3: mov edx, dword ptr [rcx + rbx]
008111c6: lea rdi, [rip + 0xe44243]
008111cd: call 0x8406a0
008111d2: test al, al
008111d4: jne 0x81120c
008111d6: movzx eax, word ptr [r12 + 0x30]
008111dc: inc r15d
008111df: inc r13
008111e2: add rbx, 0x10
008111e6: movsx rcx, ax
008111ea: cmp r13, rcx
008111ed: jl 0x8111b0
008111ef: test r15d, r15d
008111f2: je 0x8111f8
008111f4: xor eax, eax
008111f6: jmp 0x811218
008111f8: mov esi, dword ptr [r14 + 8]
008111fc: lea rdi, [rip + 0xe4420d]
00811203: call 0x840670
00811208: test al, al
0081120a: je 0x811216
0081120c: or byte ptr [r12 + 0xe], 8
00811212: mov al, 1
00811214: jmp 0x811218
00811216: xor eax, eax
00811218: add rsp, 8
0081121c: pop rbx
0081121d: pop r12
0081121f: pop r13
00811221: pop r14
00811223: pop r15
00811225: pop rbp
00811226: ret 
00811227: nop 
00811228: nop 
00811229: nop 
0081122a: nop 
0081122b: nop 
0081122c: nop 
0081122d: nop 
0081122e: nop 
0081122f: nop 
00811230: push rbp
00811231: mov rbp, rsp
00811234: push r15
00811236: push r14
00811238: push r13
0081123a: push r12
0081123c: push rbx
0081123d: push rax
0081123e: mov r13, rdi
00811241: mov edi, 0xe1a8c886
00811246: mov rdx, qword ptr [r13 + 0x40]
0081124a: movsx esi, word ptr [r13 + 0x30]
0081124f: call 0x7ae390
00811254: mov r15, rax
00811257: mov al, 1
00811259: test r15, r15
0081125c: je 0x8112dc
0081125e: mov ax, word ptr [r13 + 0x30]
00811263: test ax, ax
00811266: jle 0x8112c8
00811268: xor ebx, ebx
0081126a: mov r14d, 8
00811270: xor r12d, r12d
00811273: nop word ptr cs:[rax + rax]
00811280: mov rcx, qword ptr [r13 + 0x40]
00811284: cmp dword ptr [rcx + r14 - 8], 0x3da64e6a
0081128d: jne 0x8112af
0081128f: mov esi, dword ptr [r15 + 8]
00811293: mov edx, dword ptr [rcx + r14]
00811297: lea rdi, [rip + 0xe44172]

FUNCTION 0x80f440
0080f440: push rbp
0080f441: mov rbp, rsp
0080f444: push r15
0080f446: push r14
0080f448: push r13
0080f44a: push r12
0080f44c: push rbx
0080f44d: sub rsp, 0xe8
0080f454: mov r13, qword ptr [rdi + 0x28]
0080f458: vmovaps xmm12, xmm0
0080f45c: mov r8, rcx
0080f45f: mov r15, rdx
0080f462: mov qword ptr [rbp - 0xc8], r8
0080f469: vmovaps xmmword ptr [rbp - 0xc0], xmm12
0080f471: test r15, r15
0080f474: mov rax, qword ptr [r13 + 8]
0080f478: vmovups xmm0, xmmword ptr [rax]
0080f47c: je 0x80f482
0080f47e: mov byte ptr [r15], 0
0080f482: vpermilps xmm13, xmm12, 0
0080f488: test r8, r8
0080f48b: vmovaps xmmword ptr [rbp - 0xe0], xmm13
0080f493: je 0x80f4a1
0080f495: test r13, r13
0080f498: jne 0x80f4fe
0080f49a: xor eax, eax
0080f49c: jmp 0x80fe79
0080f4a1: vpermilps xmm1, xmm0, 0xff
0080f4a7: xor eax, eax
0080f4a9: vaddps xmm1, xmm13, xmm1
0080f4ad: vblendps xmm0, xmm0, xmm1, 8
0080f4b3: vmovups xmm1, xmmword ptr [rsi]
0080f4b7: vsubps xmm1, xmm1, xmm0
0080f4bb: vmulps xmm0, xmm0, xmm0
0080f4bf: vpermilps xmm0, xmm0, 0xff
0080f4c5: vmulps xmm1, xmm1, xmm1
0080f4c9: vpermilps xmm2, xmm1, 0x39
0080f4cf: vaddps xmm2, xmm1, xmm2
0080f4d3: vpermilpd xmm1, xmm1, 1
0080f4d9: vaddps xmm1, xmm1, xmm2
0080f4dd: vpermilps xmm1, xmm1, 0
0080f4e3: vcmpltps xmm0, xmm1, xmm0
0080f4e8: vmovmskps ecx, xmm0
0080f4ec: cmp ecx, 0xf
0080f4ef: jne 0x80fe79
0080f4f5: test r13, r13
0080f4f8: je 0x80fe79
0080f4fe: vxorps xmm0, xmm12, xmmword ptr [rip + 0x91f31a]
0080f506: vmovss xmm1, dword ptr [rip + 0x91f382]
0080f50e: vmovaps xmm15, xmmword ptr [rip + 0x91f32a]
0080f516: vmovaps xmm9, xmmword ptr [rip + 0x91f332]
0080f51e: vmovups xmm8, xmmword ptr [rip + 0x91f33a]
0080f526: vxorps xmm14, xmm14, xmm14
0080f52b: test r8, r8
0080f52e: vsubps xmm2, xmm14, xmm13
0080f533: sete byte ptr [rbp - 0xe1]
0080f53a: xor r12d, r12d
0080f53d: vmovaps xmmword ptr [rbp - 0x110], xmm2
0080f545: vmovss dword ptr [rbp - 0x44], xmm1
0080f54a: vmovaps xmmword ptr [rbp - 0x100], xmm0
0080f552: jmp 0x80f5e0
0080f557: vsubps xmm3, xmm6, xmm1
0080f55b: vsubps xmm11, xmm9, xmm1
0080f55f: vxorps xmm2, xmm3, xmmword ptr [rip + 0x91f2b9]
0080f567: vmovshdup xmm1, xmm3
0080f56b: vmulss xmm4, xmm3, xmm3
0080f56f: vmulss xmm10, xmm1, xmm1
0080f573: vaddss xmm4, xmm4, xmm10
0080f578: vinsertps xmm1, xmm1, xmm2, 0x10
0080f57e: vsqrtss xmm4, xmm0, xmm4
0080f582: vucomiss xmm4, dword ptr [rip + 0x91f30a]
0080f58a: jbe 0x80f5a0
0080f58c: vmovss xmm2, dword ptr [rip + 0x91f304]
0080f594: vdivss xmm2, xmm2, xmm4
0080f598: vmovsldup xmm2, xmm2
0080f59c: vmulps xmm1, xmm1, xmm2
0080f5a0: vmulps xmm1, xmm11, xmm1
0080f5a4: vmovaps xmm9, xmmword ptr [rip + 0x91f2a4]
0080f5ac: vmovshdup xmm2, xmm1
0080f5b0: vaddss xmm1, xmm1, xmm2
0080f5b4: vucomiss xmm1, dword ptr [rip + 0x91f2e0]
0080f5bc: jbe 0x80fe17
0080f5c2: lea rax, [r9 + 0x60]
0080f5c6: lea rdi, [r9 + 0x64]
0080f5ca: vmovshdup xmm5, xmm11
0080f5cf: jmp 0x80fd57
0080f5d4: nop word ptr cs:[rax + rax]
0080f5e0: mov eax, dword ptr [r13 + 0x10]
0080f5e4: movzx ecx, ax
0080f5e7: cmp ecx, 3
0080f5ea: je 0x80f8d0
0080f5f0: cmp ecx, 1
0080f5f3: je 0x80f710
0080f5f9: test ecx, ecx
0080f5fb: jne 0x80fe60
0080f601: vmovups xmm0, xmmword ptr [r13 + 0x20]
0080f607: vmovups xmm2, xmmword ptr [rsi]
0080f60b: mov al, 1
0080f60d: vsubps xmm1, xmm0, xmm2
0080f611: vmulps xmm1, xmm1, xmm1
0080f615: vpermilps xmm3, xmm1, 0x39
0080f61b: vaddps xmm3, xmm1, xmm3
0080f61f: vpermilpd xmm1, xmm1, 1
0080f625: vaddps xmm1, xmm1, xmm3
0080f629: vpermilps xmm1, xmm1, 0
0080f62f: vrsqrtps xmm3, xmm1
0080f633: vmulps xmm4, xmm3, xmm3
0080f637: vmulps xmm5, xmm3, xmm9
0080f63c: vmulps xmm4, xmm4, xmm1
0080f640: vaddps xmm4, xmm4, xmm15
0080f645: vsubps xmm4, xmm14, xmm4
0080f649: vmulps xmm4, xmm5, xmm4
0080f64d: vaddps xmm3, xmm3, xmm4
0080f651: vmulps xmm3, xmm1, xmm3
0080f655: vcmpleps xmm1, xmm8, xmm1
0080f65a: vandps xmm1, xmm3, xmm1
0080f65e: vpermilps xmm3, xmm0, 0xe7
0080f664: vaddss xmm3, xmm3, xmm12
0080f669: vucomiss xmm3, xmm1
0080f66d: setae cl
0080f670: jae 0x80f675
0080f672: mov al, r12b
0080f675: or cl, byte ptr [rbp - 0xe1]
0080f67b: jne 0x80f6e6
0080f67d: vmovss xmm3, dword ptr [rbp - 0x44]
0080f682: vucomiss xmm3, xmm1
0080f686: jbe 0x80f6e3
0080f688: vsubps xmm2, xmm2, xmm0
0080f68c: vpermilps xmm3, xmm0, 0xff
0080f692: vmulps xmm4, xmm2, xmm2
0080f696: vpermilps xmm5, xmm4, 0x39
0080f69c: vaddps xmm5, xmm4, xmm5
0080f6a0: vpermilpd xmm4, xmm4, 1
0080f6a6: vaddps xmm4, xmm4, xmm5
0080f6aa: vpermilps xmm4, xmm4, 0
0080f6b0: vrsqrtps xmm5, xmm4
0080f6b4: vmulps xmm6, xmm5, xmm5
0080f6b8: vmulps xmm4, xmm4, xmm6
0080f6bc: vmulps xmm6, xmm5, xmm9
0080f6c1: vaddps xmm4, xmm4, xmm15
0080f6c6: vsubps xmm4, xmm14, xmm4
0080f6ca: vmulps xmm4, xmm6, xmm4
0080f6ce: vaddps xmm4, xmm5, xmm4
0080f6d2: vmulps xmm2, xmm2, xmm4
0080f6d6: vmulps xmm2, xmm3, xmm2
0080f6da: vaddps xmm0, xmm0, xmm2
0080f6de: vmovups xmmword ptr [r8], xmm0
0080f6e3: mov al, r12b
0080f6e6: test r15, r15
0080f6e9: je 0x80fc39
0080f6ef: vbroadcastss xmm0, dword ptr [r13 + 0x2c]
0080f6f5: vsubss xmm0, xmm0, xmm12
0080f6fa: vucomiss xmm0, xmm1
0080f6fe: jae 0x80fc41
0080f704: mov r12b, al
0080f707: jmp 0x80fe60
0080f70c: nop dword ptr [rax]
0080f710: vmovups xmm0, xmmword ptr [rip + 0x91f158]
0080f718: shr eax, 0x10
0080f71b: mov r9d, 0
0080f721: je 0x80f795
0080f723: vmovaps xmm0, xmmword ptr [rip + 0x91f155]
0080f72b: vmovups xmm2, xmmword ptr [rip + 0x91f13d]
0080f733: lea rcx, [r13 + 0x60]
0080f737: neg rax
0080f73a: xor r9d, r9d
0080f73d: vblendps xmm1, xmm0, xmmword ptr [rsi], 7
0080f743: nop word ptr cs:[rax + rax]
0080f750: vmulps xmm0, xmm1, xmmword ptr [rcx]
0080f754: lea rbx, [rcx - 0x40]
0080f758: vpermilps xmm3, xmm0, 0x39
0080f75e: vaddps xmm0, xmm0, xmm3
0080f762: vpermilpd xmm3, xmm0, 1
0080f768: vaddps xmm0, xmm0, xmm3
0080f76c: vpermilps xmm0, xmm0, 0
0080f772: vcmpltps xmm3, xmm2, xmm0
0080f777: vmovmskps edi, xmm3
0080f77b: cmp edi, 0xf
0080f77e: je 0x80f784
0080f780: vmovaps xmm0, xmm2
0080f784: cmove r9, rbx
0080f788: add rcx, 0x70
0080f78c: vmovaps xmm2, xmm0
0080f790: inc rax
0080f793: jne 0x80f750
0080f795: mov bl, 1
0080f797: vucomiss xmm12, xmm0
0080f79b: ja 0x80f7a0
0080f79d: mov bl, r12b
0080f7a0: test r8, r8
0080f7a3: je 0x80fe34
0080f7a9: mov al, bl
0080f7ab: and al, 1
0080f7ad: jne 0x80fe34
0080f7b3: vmovups xmm8, xmmword ptr [r9]
0080f7b8: vmovups xmm3, xmmword ptr [rsi]
0080f7bc: vpermilps xmm2, xmmword ptr [r9 + 0x40], 0x64
0080f7c3: vmovups xmm1, xmmword ptr [r9 + 0x30]
0080f7c9: vmovq xmm6, qword ptr [r9 + 0x68]
0080f7cf: vsubps xmm4, xmm3, xmm8
0080f7d4: vmulps xmm4, xmm2, xmm4
0080f7d8: vpermilps xmm5, xmm4, 0x39
0080f7de: vaddps xmm5, xmm4, xmm5
0080f7e2: vpermilpd xmm4, xmm4, 1
0080f7e8: vaddps xmm4, xmm4, xmm5
0080f7ec: vpermilps xmm4, xmm4, 0
0080f7f2: vmulps xmm2, xmm2, xmm4
0080f7f6: vpermilps xmm4, xmm1, 0xff
0080f7fc: vsubps xmm5, xmm3, xmm2
0080f800: vpermilps xmm2, xmm1, 9
0080f806: vpermilps xmm3, xmm5, 9
0080f80c: vmulps xmm2, xmm2, xmm5
0080f810: vmulps xmm3, xmm1, xmm3
0080f814: vsubps xmm2, xmm3, xmm2
0080f818: vpermilps xmm3, xmm2, 9
0080f81e: vmulps xmm4, xmm4, xmm3
0080f822: vpermilps xmm3, xmm3, 9
0080f828: vmulps xmm3, xmm1, xmm3
0080f82c: vmulps xmm1, xmm1, xmm2
0080f830: vpermilps xmm1, xmm1, 9
0080f836: vsubps xmm1, xmm3, xmm1
0080f83a: vpermilps xmm1, xmm1, 9
0080f840: vaddps xmm1, xmm4, xmm1
0080f844: vaddps xmm1, xmm1, xmm1
0080f848: vaddps xmm1, xmm5, xmm1
0080f84c: vaddps xmm9, xmm1, xmmword ptr [r9 + 0x20]
0080f852: vmovq xmm1, qword ptr [r9 + 0x50]
0080f858: vsubps xmm3, xmm1, xmm6
0080f85c: vxorps xmm2, xmm3, xmmword ptr [rip + 0x91efbc]
0080f864: vmovshdup xmm7, xmm3
0080f868: vmulss xmm4, xmm3, xmm3
0080f86c: vsubps xmm11, xmm9, xmm6
0080f870: vmulss xmm10, xmm7, xmm7
0080f874: vaddss xmm4, xmm4, xmm10
0080f879: vinsertps xmm7, xmm7, xmm2, 0x10
0080f87f: vsqrtss xmm4, xmm0, xmm4
0080f883: vucomiss xmm4, dword ptr [rip + 0x91f009]
0080f88b: jbe 0x80f8a1
0080f88d: vmovss xmm2, dword ptr [rip + 0x91f003]
0080f895: vdivss xmm2, xmm2, xmm4
0080f899: vmovsldup xmm2, xmm2
0080f89d: vmulps xmm7, xmm7, xmm2
0080f8a1: vmulps xmm2, xmm11, xmm7
0080f8a5: vmovshdup xmm4, xmm2
0080f8a9: vaddss xmm2, xmm2, xmm4
0080f8ad: vucomiss xmm2, dword ptr [rip + 0x91efe7]
0080f8b5: jbe 0x80fc51
0080f8bb: lea rax, [r9 + 0x68]
0080f8bf: lea rdi, [r9 + 0x6c]
0080f8c3: jmp 0x80fd4a
0080f8c8: nop dword ptr [rax + rax]
0080f8d0: vmovups xmm0, xmmword ptr [r13 + 0x30]
0080f8d6: vmovups xmm7, xmmword ptr [rip + 0x91ef52]
0080f8de: vmovups xmm10, xmmword ptr [r13 + 0x20]
0080f8e4: vbroadcastss xmm11, dword ptr [r13 + 0x44]
0080f8ea: vaddps xmm1, xmm0, xmm0