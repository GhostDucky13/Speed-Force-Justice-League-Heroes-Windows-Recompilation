/* jlh_upscale.h - the upscalers' bridge (jlh_upscale.dll, built with MSVC
 * because NVIDIA's NGX libraries are MSVC static libraries). Loaded at run
 * time by the D3D11 backend; every call takes D3D11 objects of its device.
 *
 * Motion vectors: previous minus current position, in UV units of the
 * render target (the backend's R16G16 motion target); mv_scale converts to
 * render pixels (in_w, in_h). Jitter: the sub-pixel offset the frame was
 * drawn with, in render pixels. */
#ifndef JLH_UPSCALE_H
#define JLH_UPSCALE_H
#ifdef __cplusplus
extern "C" {
#endif
struct ID3D11Device;
struct ID3D11DeviceContext;
struct ID3D11Resource;

enum { JLHU_DLSS = 1, JLHU_FSR = 2, JLHU_XESS = 3 };

typedef struct jlhu_eval {
    struct ID3D11Resource *color;   /* render-size colour */
    struct ID3D11Resource *depth;   /* render-size R32_FLOAT depth */
    struct ID3D11Resource *mv;      /* render-size R16G16_FLOAT motion */
    struct ID3D11Resource *out;     /* output-size R8G8B8A8_UNORM, UAV */
    float jitter_x, jitter_y;       /* render pixels */
    float mv_scale_x, mv_scale_y;   /* motion units -> render pixels */
    unsigned in_w, in_h;
    int reset;
    float frame_ms;
} jlhu_eval;

typedef int  (*jlhu_create_fn)(int which, struct ID3D11Device *dev, struct ID3D11DeviceContext *ctx,
                               unsigned in_w, unsigned in_h, unsigned out_w, unsigned out_h);
typedef int  (*jlhu_evaluate_fn)(struct ID3D11DeviceContext *ctx, const jlhu_eval *e);
typedef void (*jlhu_destroy_fn)(void);
typedef const char *(*jlhu_error_fn)(void);

#ifdef __cplusplus
}
#endif
#endif
