#pragma once
using SceUID = int;
int sceKernelGetThreadId();
int sceKernelGetThreadCpuAffinityMask(SceUID);
int sceKernelChangeThreadCpuAffinityMask(SceUID, int);

int sceKernelDelayThread(unsigned microseconds);
