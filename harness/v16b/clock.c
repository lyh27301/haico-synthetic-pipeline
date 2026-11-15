/* Step 16c: the task's date for the agent, with nothing in the agent's environment.
 *
 * Built into the step-16c image as /usr/lib/x86_64-linux-gnu/libclock.so.1 and listed in /etc/ld.so.preload, so the
 * dynamic loader maps it into every process without any environment variable (no LD_PRELOAD, no FAKETIME*).
 * It acts only in processes whose real and effective uid are both the agent's (1000): root processes (agent-server,
 * MCP server, evaluator) and setuid programs (sudo for chat_npc, whose effective uid is 0) keep the real clock, so the
 * NPC helper does not hang as it did with libfaketime in step 16b.
 *
 * In the agent's processes it shifts the wall clock by a fixed offset (seconds): time, gettimeofday, clock_gettime and
 * timespec_get for the realtime clocks; file times returned by the stat family are shifted the same way, and times the
 * agent sets (utimensat / futimens / utimes / utime) are shifted back, so files made now show the task's date and a
 * file touched to a date keeps that date. Monotonic clocks are untouched.
 *
 * The offset is not read from a file or variable: it is a constant in this library's data, after a 16-byte marker,
 * which the harness rewrites (as root, a new file renamed over the old one) before the agent's terminal starts.
 * Statically linked programs are not affected (same limit as libfaketime).
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include <utime.h>

#define AGENT_UID 1000

struct shift { char magic[16]; int64_t offset; };
__attribute__((used)) volatile struct shift CLOCK_SHIFT = {{'O','H','1','6','C','_','C','L','O','C','K','_','O','F','F','\0'}, 0};

static int active = -1;
static int64_t off;

static int on(void) {
    if (active < 0) {
        off = CLOCK_SHIFT.offset;
        active = (getuid() == AGENT_UID && geteuid() == AGENT_UID && off != 0);
    }
    return active;
}

#define NEXT(name) static __typeof__(name) *real_##name; if (!real_##name) real_##name = dlsym(RTLD_NEXT, #name)

static int realtime(clockid_t c) {
    return c == CLOCK_REALTIME || c == CLOCK_REALTIME_COARSE || c == CLOCK_TAI || c == CLOCK_REALTIME_ALARM;
}

int clock_gettime(clockid_t c, struct timespec *ts) {
    NEXT(clock_gettime);
    int r = real_clock_gettime(c, ts);
    if (r == 0 && ts && realtime(c) && on()) ts->tv_sec += off;
    return r;
}

time_t time(time_t *t) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    if (t) *t = ts.tv_sec;
    return ts.tv_sec;
}

int gettimeofday(struct timeval *restrict tv, void *restrict tz) {
    NEXT(gettimeofday);
    int r = real_gettimeofday(tv, tz);
    if (r == 0 && tv && on()) tv->tv_sec += off;
    return r;
}

int timespec_get(struct timespec *ts, int base) {
    NEXT(timespec_get);
    int r = real_timespec_get(ts, base);
    if (r == TIME_UTC && ts && on()) ts->tv_sec += off;
    return r;
}

/* ---- file times: + offset when read, - offset when set */
static void shift_st(struct stat *s) {
    if (s && on()) { s->st_atim.tv_sec += off; s->st_mtim.tv_sec += off; s->st_ctim.tv_sec += off; }
}
static void shift_stx(struct statx *s) {
    if (s && on()) { s->stx_atime.tv_sec += off; s->stx_mtime.tv_sec += off; s->stx_ctime.tv_sec += off;
                     s->stx_btime.tv_sec += off; }
}

int stat(const char *restrict p, struct stat *restrict s) { NEXT(stat); int r = real_stat(p, s); if (!r) shift_st(s); return r; }
int lstat(const char *restrict p, struct stat *restrict s) { NEXT(lstat); int r = real_lstat(p, s); if (!r) shift_st(s); return r; }
int fstat(int fd, struct stat *s) { NEXT(fstat); int r = real_fstat(fd, s); if (!r) shift_st(s); return r; }
int fstatat(int d, const char *restrict p, struct stat *restrict s, int f) {
    NEXT(fstatat); int r = real_fstatat(d, p, s, f); if (!r) shift_st(s); return r; }
int stat64(const char *restrict p, struct stat64 *restrict s) {
    NEXT(stat64); int r = real_stat64(p, s); if (!r) shift_st((struct stat *)s); return r; }
int lstat64(const char *restrict p, struct stat64 *restrict s) {
    NEXT(lstat64); int r = real_lstat64(p, s); if (!r) shift_st((struct stat *)s); return r; }
int fstat64(int fd, struct stat64 *s) { NEXT(fstat64); int r = real_fstat64(fd, s); if (!r) shift_st((struct stat *)s); return r; }
int fstatat64(int d, const char *restrict p, struct stat64 *restrict s, int f) {
    NEXT(fstatat64); int r = real_fstatat64(d, p, s, f); if (!r) shift_st((struct stat *)s); return r; }
int statx(int d, const char *restrict p, int f, unsigned int m, struct statx *restrict s) {
    NEXT(statx); int r = real_statx(d, p, f, m, s); if (!r) shift_stx(s); return r; }

static void unshift_ts(struct timespec t[2], struct timespec out[2]) {
    for (int i = 0; i < 2; i++) {
        out[i] = t[i];
        if (t[i].tv_nsec != UTIME_NOW && t[i].tv_nsec != UTIME_OMIT) out[i].tv_sec -= off;
    }
}

int utimensat(int d, const char *p, const struct timespec t[2], int f) {
    NEXT(utimensat);
    if (!t || !on()) return real_utimensat(d, p, t, f);
    struct timespec o[2]; unshift_ts((struct timespec *)t, o); return real_utimensat(d, p, o, f);
}
int futimens(int fd, const struct timespec t[2]) {
    NEXT(futimens);
    if (!t || !on()) return real_futimens(fd, t);
    struct timespec o[2]; unshift_ts((struct timespec *)t, o); return real_futimens(fd, o);
}
int utimes(const char *p, const struct timeval t[2]) {
    NEXT(utimes);
    if (!t || !on()) return real_utimes(p, t);
    struct timeval o[2] = {t[0], t[1]}; o[0].tv_sec -= off; o[1].tv_sec -= off; return real_utimes(p, o);
}
int utime(const char *p, const struct utimbuf *t) {
    NEXT(utime);
    if (!t || !on()) return real_utime(p, t);
    struct utimbuf o = *t; o.actime -= off; o.modtime -= off; return real_utime(p, &o);
}
