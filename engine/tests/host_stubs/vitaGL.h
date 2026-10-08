#pragma once
#include <cstddef>
using GLuint = unsigned;
constexpr unsigned GL_ARRAY_BUFFER = 0x8892, GL_STATIC_DRAW = 0x88E4;
void glGenBuffers(int, GLuint*);
void glBindBuffer(unsigned, GLuint);
void glBufferData(unsigned, size_t, const void*, unsigned);
