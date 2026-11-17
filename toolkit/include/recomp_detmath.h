/*
 * recomp_detmath.h - the x87 transcendentals with the same result on every PC.
 *
 * The lifter turns FSIN/FCOS/FPTAN/FPATAN/FYL2X/F2XM1 into sin, cos, tan,
 * atan2, log2 and expm1 (through the recomp_x87_* helpers in recomp_types.h).
 * Taken from the C library, their last bit depends on whose C library it is:
 * Windows' ucrtbase, Wine's ucrtbase (a different implementation, used under
 * Wine and Proton) and even ucrtbase's own FMA3 and SSE2 paths differ on some
 * inputs. For one player that is invisible. For online play, where two PCs
 * must compute bit-identical game states, a one-ulp difference in an angle
 * becomes a desync a few seconds later, so a Windows PC and a Linux PC could
 * not play together.
 *
 * These are compiled into the game, from basic IEEE arithmetic only (+, -, *,
 * /, sqrt, frexp, integer operations), which every x86-64 CPU and OS rounds
 * the same way: the same input gives the same bits on any PC. The generated
 * code is built without FMA contraction (no -mfma / -march), which keeps it
 * so.
 *
 * The algorithms are the Go standard library's pure-Go math package (itself
 * from Cephes and FreeBSD's msun), translated to C: sin/cos/tan (with Go's
 * Payne-Hanek reduction for every argument from pi/4 up), atan2, log2 (as
 * log / ln 2), expm1. Accuracy is within about 1-2 ulp of the true value, like the C
 * libraries they replace. Go's license (BSD-3-Clause) is below.
 *
 * The Go math code these are translated from:
 *
 * Copyright 2009 The Go Authors.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met:
 *
 *    * Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 *    * Redistributions in binary form must reproduce the above
 * copyright notice, this list of conditions and the following disclaimer
 * in the documentation and/or other materials provided with the
 * distribution.
 *    * Neither the name of Google LLC nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 * recomp_types.h includes this after <math.h> and maps the six names onto it
 * for the generated code. Define RECOMP_HOST_LIBM to keep the C library's.
 */
#ifndef RECOMP_DETMATH_H
#define RECOMP_DETMATH_H

#include <math.h>
#include <stdint.h>
#include <string.h>

static inline uint64_t recomp_dm_bits(double x) { uint64_t u; memcpy(&u, &x, 8); return u; }
static inline double recomp_dm_from(uint64_t u) { double x; memcpy(&x, &u, 8); return x; }

#define RECOMP_DM_PI 3.14159265358979323846264338327950288

/* Payne-Hanek: x >= pi/4 into an octant j and a remainder z in [-pi/4, pi/4]. */
static inline double recomp_dm_reduce(double x, uint64_t *jp)
{
    static const uint64_t m[] = {
        0x0000000000000001ull, 0x45f306dc9c882a53ull, 0xf84eafa3ea69bb81ull, 0xb6c52b3278872083ull,
        0xfca2c757bd778ac3ull, 0x6e48dc74849ba5c0ull, 0x0c925dd413a32439ull, 0xfc3bd63962534e7dull,
        0xd1046bea5d768909ull, 0xd338e04d68befc82ull, 0x7323ac7306a673e9ull, 0x3908bf177bf25076ull,
        0x3ff12fffbc0b301full, 0xde5e2316b414da3eull, 0xda6cfd9e4f96136eull, 0x9e8c7ecd3cbfd45aull,
        0xea4f758fd7cbe2f6ull, 0x7a0e73ef14a525d4ull, 0xd7f6bf623f1aba10ull, 0xac06608df8f6d757ull,
    };
    uint64_t ix = recomp_dm_bits(x), z0, z1, z2, z2hi, z1hi, z1lo, z0lo, lo, hi, j, e, fh;
    unsigned __int128 p, f;
    int ex = (int)((ix >> 52) & 0x7ff) - 1023 - 52, lz, c, neg = 0;
    unsigned digit, bs;
    double z;
    if (x < RECOMP_DM_PI / 4) {
        *jp = 0;
        return x;
    }
    ix &= ~(0x7ffull << 52);
    ix |= 1ull << 52;
    digit = (unsigned)(ex + 61) / 64;
    bs = (unsigned)(ex + 61) % 64;
    z0 = (m[digit] << bs) | (bs ? m[digit + 1] >> (64 - bs) : 0);
    z1 = (m[digit + 1] << bs) | (bs ? m[digit + 2] >> (64 - bs) : 0);
    z2 = (m[digit + 2] << bs) | (bs ? m[digit + 3] >> (64 - bs) : 0);
    p = (unsigned __int128)z2 * ix;
    z2hi = (uint64_t)(p >> 64);
    p = (unsigned __int128)z1 * ix;
    z1hi = (uint64_t)(p >> 64);
    z1lo = (uint64_t)p;
    z0lo = z0 * ix;
    lo = z1lo + z2hi;
    c = lo < z1lo;
    hi = z0lo + z1hi + (uint64_t)c;
    j = hi >> 61;
    /* The fraction below the octant, as 128 bits. Go turns it into a double
     * first and subtracts 1 for odd octants, which cancels near the zeros;
     * taking 1 - f here in integers keeps every bit. */
    f = (unsigned __int128)(hi << 3 | lo >> 61) << 64 | (unsigned __int128)(lo << 3);
    if (j & 1) {
        f = -f;
        neg = 1;
        j = (j + 1) & 7;
    }
    *jp = j;
    if (!f)
        return 0.0;
    fh = (uint64_t)(f >> 64);
    lz = fh ? __builtin_clzll(fh) : 64 + __builtin_clzll((uint64_t)f);
    f <<= lz;                                   /* leading 1 at bit 127 */
    hi = (uint64_t)(f >> 75);                   /* 53 bits, implicit 1 included */
    e = (uint64_t)(int64_t)(1023 - 1 - lz);
    z = recomp_dm_from((hi & ((1ull << 52) - 1)) | e << 52);
    z *= RECOMP_DM_PI / 4;
    return neg ? -z : z;
}

/* x >= 0: the octant and the remainder, as the three trig functions share. */
/* Go reduces below 2^29 with a three-part pi/4 (Cody-Waite), which loses
 * relative accuracy near the zeros (up to a few hundred ulp by 1e4); the
 * exact reduction is cheap enough to use from pi/4 up, which keeps sin, cos
 * and tan within about 1 ulp everywhere. */
static inline double recomp_dm_octant(double x, uint64_t *jp, int for_tan)
{
    (void)for_tan;
    if (x < RECOMP_DM_PI / 4) {
        *jp = 0;
        return x;
    }
    return recomp_dm_reduce(x, jp);
}

static inline double recomp_dm_ksin(double z)
{
    double zz = z * z;
    return z + z * zz * ((((((1.58962301576546568060e-10 * zz) + -2.50507477628578072866e-8) * zz +
                             2.75573136213857245213e-6) * zz + -1.98412698295895385996e-4) * zz +
                           8.33333333332211858878e-3) * zz + -1.66666666666666307295e-1);
}

static inline double recomp_dm_kcos(double z)
{
    double zz = z * z;
    return 1.0 - 0.5 * zz + zz * zz * ((((((-1.13585365213876817300e-11 * zz) + 2.08757008419747316778e-9) * zz +
                                          -2.75573141792967388112e-7) * zz + 2.48015872888517045348e-5) * zz +
                                        -1.38888888888730564116e-3) * zz + 4.16666666666665929218e-2);
}

static inline double recomp_dm_sin(double x)
{
    uint64_t j;
    int sign = 0;
    double z, y;
    if (x == 0 || x != x)
        return x;
    if (isinf(x))
        return NAN;
    if (x < 0) {
        x = -x;
        sign = 1;
    }
    z = recomp_dm_octant(x, &j, 0);
    if (j > 3) {
        sign = !sign;
        j -= 4;
    }
    y = (j == 1 || j == 2) ? recomp_dm_kcos(z) : recomp_dm_ksin(z);
    return sign ? -y : y;
}

static inline double recomp_dm_cos(double x)
{
    uint64_t j;
    int sign = 0;
    double z, y;
    if (x != x || isinf(x))
        return NAN;
    x = fabs(x);
    z = recomp_dm_octant(x, &j, 0);
    if (j > 3) {
        j -= 4;
        sign = !sign;
    }
    if (j > 1)
        sign = !sign;
    y = (j == 1 || j == 2) ? recomp_dm_ksin(z) : recomp_dm_kcos(z);
    return sign ? -y : y;
}

static inline double recomp_dm_tan(double x)
{
    uint64_t j;
    int sign = 0;
    double z, zz, y;
    if (x == 0 || x != x)
        return x;
    if (isinf(x))
        return NAN;
    if (x < 0) {
        x = -x;
        sign = 1;
    }
    z = recomp_dm_octant(x, &j, 1);
    zz = z * z;
    if (zz > 1e-14)
        y = z + z * (zz * (((-1.30936939181383777646e4 * zz) + 1.15351664838587416140e6) * zz +
                           -1.79565251976484877988e7) /
                     ((((zz + 1.36812963470692954678e4) * zz + -1.32089234440210967447e6) * zz +
                       2.50083801823357915839e7) * zz + -5.38695755929454629881e7));
    else
        y = z;
    if (j & 2)
        y = -1 / y;
    return sign ? -y : y;
}

static inline double recomp_dm_xatan(double x)
{
    double z = x * x;
    z = z * ((((-8.750608600031904122785e-01 * z + -1.615753718733365076637e+01) * z + -7.500855792314704667340e+01) * z +
              -1.228866684490136173410e+02) * z + -6.485021904942025371773e+01) /
        (((((z + 2.485846490142306297962e+01) * z + 1.650270098316988542046e+02) * z + 4.328810604912902668951e+02) * z +
          4.853903996359136964868e+02) * z + 1.945506571482613964425e+02);
    return x * z + x;
}

static inline double recomp_dm_satan(double x)
{
    const double more = 6.123233995736765886130e-17;    /* pi/2 = PIO2 + more */
    if (x <= 0.66)
        return recomp_dm_xatan(x);
    if (x > 2.41421356237309504880)                    /* tan(3pi/8) */
        return RECOMP_DM_PI / 2 - recomp_dm_xatan(1 / x) + more;
    return RECOMP_DM_PI / 4 + recomp_dm_xatan((x - 1) / (x + 1)) + 0.5 * more;
}

static inline double recomp_dm_atan2(double y, double x)
{
    double q;
    if (y != y || x != x)
        return NAN;
    if (y == 0) {
        if (x >= 0 && !signbit(x))
            return copysign(0.0, y);
        return copysign(RECOMP_DM_PI, y);
    }
    if (x == 0)
        return copysign(RECOMP_DM_PI / 2, y);
    if (isinf(x)) {
        if (x > 0)
            return isinf(y) ? copysign(RECOMP_DM_PI / 4, y) : copysign(0.0, y);
        return isinf(y) ? copysign(3 * RECOMP_DM_PI / 4, y) : copysign(RECOMP_DM_PI, y);
    }
    if (isinf(y))
        return copysign(RECOMP_DM_PI / 2, y);
    q = y / x;
    q = q == 0 ? q : (q > 0 ? recomp_dm_satan(q) : -recomp_dm_satan(-q));
    if (x < 0)
        return q <= 0 ? q + RECOMP_DM_PI : q - RECOMP_DM_PI;
    return q;
}

static inline double recomp_dm_log(double x)
{
    const double ln2hi = 6.93147180369123816490e-01, ln2lo = 1.90821492927058770002e-10;
    double f1, f, k, s, s2, s4, t1, t2, r, hfsq;
    int ki;
    if (x != x || (isinf(x) && x > 0))
        return x;
    if (x < 0)
        return NAN;
    if (x == 0)
        return -INFINITY;
    f1 = frexp(x, &ki);
    if (f1 < 0.70710678118654752440 / 1.0) {    /* sqrt(2)/2 */
        f1 *= 2;
        ki--;
    }
    f = f1 - 1;
    k = (double)ki;
    s = f / (2 + f);
    s2 = s * s;
    s4 = s2 * s2;
    t1 = s2 * (6.666666666666735130e-01 + s4 * (2.857142874366239149e-01 + s4 * (1.818357216161805012e-01 +
                                                                                  s4 * 1.479819860511658591e-01)));
    t2 = s4 * (3.999999999940941908e-01 + s4 * (2.222219843214978396e-01 + s4 * 1.531383769920937332e-01));
    r = t1 + t2;
    hfsq = 0.5 * f * f;
    return k * ln2hi - ((hfsq - (s * (hfsq + r) + k * ln2lo)) - f);
}

static inline double recomp_dm_log2(double x)
{
    int e;
    double frac = frexp(x, &e);
    if (frac == 0.5)            /* exact powers of two give exact answers */
        return (double)(e - 1);
    /* log(x) / ln 2 rather than Go's log(frac) / ln 2 + e, which cancels to
     * thousands of ulp just above 1 */
    return recomp_dm_log(x) * (1 / 0.693147180559945309417232121458176568);
}

static inline double recomp_dm_expm1(double x)
{
    const double othreshold = 7.09782712893383973096e+02, ln2x56 = 3.88162421113569373274e+01,
                 ln2halfx3 = 1.03972077083991796413e+00, ln2half = 3.46573590279972654709e-01,
                 ln2hi = 6.93147180369123816490e-01, ln2lo = 1.90821492927058770002e-10,
                 invln2 = 1.44269504088896338700e+00, tiny = 1.0 / (double)(1ull << 54),
                 q1 = -3.33333333333331316428e-02, q2 = 1.58730158725481460165e-03,
                 q3 = -7.93650757867487942473e-05, q4 = 4.00821782732936239552e-06,
                 q5 = -2.01099218183624371326e-07;
    double absx, c = 0, hfx, hxs, r1, t, e, y;
    int sign = 0, k;
    if ((isinf(x) && x > 0) || x != x)
        return x;
    if (isinf(x))
        return -1;
    absx = x;
    if (x < 0) {
        absx = -absx;
        sign = 1;
    }
    if (absx >= ln2x56) {
        if (sign)
            return -1;
        if (absx >= othreshold)
            return INFINITY;
    }
    if (absx > ln2half) {
        double hi, lo;
        if (absx < ln2halfx3) {
            if (!sign) {
                hi = x - ln2hi;
                lo = ln2lo;
                k = 1;
            } else {
                hi = x + ln2hi;
                lo = -ln2lo;
                k = -1;
            }
        } else {
            k = !sign ? (int)(invln2 * x + 0.5) : (int)(invln2 * x - 0.5);
            t = (double)k;
            hi = x - t * ln2hi;
            lo = t * ln2lo;
        }
        x = hi - lo;
        c = (hi - x) - lo;
    } else if (absx < tiny) {
        return x;
    } else {
        k = 0;
    }
    hfx = 0.5 * x;
    hxs = x * hfx;
    r1 = 1 + hxs * (q1 + hxs * (q2 + hxs * (q3 + hxs * (q4 + hxs * q5))));
    t = 3 - r1 * hfx;
    e = hxs * ((r1 - t) / (6.0 - x * t));
    if (k == 0)
        return x - (x * e - hxs);
    e = (x * (e - c) - c);
    e -= hxs;
    if (k == -1)
        return 0.5 * (x - e) - 0.5;
    if (k == 1) {
        if (x < -0.25)
            return -2 * (e - (x + 0.5));
        return 1 + 2 * (x - e);
    }
    if (k <= -2 || k > 56) {
        y = 1 - (e - x);
        y = recomp_dm_from(recomp_dm_bits(y) + ((uint64_t)(int64_t)k << 52));
        return y - 1;
    }
    if (k < 20) {
        t = recomp_dm_from(0x3ff0000000000000ull - (0x20000000000000ull >> k));    /* 1 - 2^-k */
        y = t - (e - x);
        return recomp_dm_from(recomp_dm_bits(y) + ((uint64_t)k << 52));
    }
    t = recomp_dm_from((uint64_t)(0x3ff - k) << 52);                                /* 2^-k */
    y = x - (e + t);
    y += 1;
    return recomp_dm_from(recomp_dm_bits(y) + ((uint64_t)k << 52));
}

#ifndef RECOMP_HOST_LIBM
#define sin(x) recomp_dm_sin(x)
#define cos(x) recomp_dm_cos(x)
#define tan(x) recomp_dm_tan(x)
#define atan2(y, x) recomp_dm_atan2(y, x)
#define log2(x) recomp_dm_log2(x)
#define expm1(x) recomp_dm_expm1(x)
#endif

#endif /* RECOMP_DETMATH_H */
