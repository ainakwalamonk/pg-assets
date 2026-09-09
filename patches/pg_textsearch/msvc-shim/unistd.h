/* MSVC shim: pg_textsearch's src/segment/segment.c includes <unistd.h> but uses no symbol from it.
   Windows has no such header. This empty stand-in keeps the upstream source unpatched.
   If a future version starts calling POSIX I/O here, this must become a real shim (io.h/process.h). */
#ifndef PG_TEXTSEARCH_MSVC_UNISTD_SHIM
#define PG_TEXTSEARCH_MSVC_UNISTD_SHIM
#endif
