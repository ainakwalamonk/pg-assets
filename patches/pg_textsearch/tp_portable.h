/*
 * Portable struct-layout attributes for pg_textsearch.
 *
 * Upstream writes GCC's TRAILING __attribute__((packed)) / ((aligned(n))) after the closing brace of a struct.
 * MSVC has no equivalent in that position, which is the only thing preventing a Windows build.
 *
 * Defining __attribute__ away is NOT an option: these structs are the on-disk index format (format.h) and the
 * arena posting layout (expull.h). Dropping `packed` compiles cleanly and silently changes the layout — an
 * index that builds and returns wrong answers, with no crash and no error.
 *
 * So packing is expressed with #pragma pack, which GCC, Clang and MSVC all implement identically, and
 * alignment with a compiler-specific specifier in the LEADING position, which all three accept. Every affected
 * struct carries a StaticAssertDecl on sizeof and alignof, so any compiler that lays it out differently fails
 * the build rather than producing a corrupt segment.
 */
#ifndef TP_PORTABLE_H
#define TP_PORTABLE_H

#if defined(_MSC_VER)
#define TP_ALIGNED(n) __declspec(align(n))
#define TP_UNUSED
#else
#define TP_ALIGNED(n) __attribute__((aligned(n)))
#define TP_UNUSED __attribute__((unused))
#endif

#endif							/* TP_PORTABLE_H */
