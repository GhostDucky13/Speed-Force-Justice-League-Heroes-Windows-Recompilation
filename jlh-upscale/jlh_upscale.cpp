// jlh_upscale.cpp - DLSS Super Resolution for the JLH D3D11 backend (FSR and
// XeSS join it later). Exports jlhu_create / jlhu_evaluate / jlhu_destroy /
// jlhu_error (jlh_upscale.h).
#include <windows.h>
#include <d3d11.h>
#include <d3d11_4.h>
#include <d3d12.h>
#include <dxgi1_4.h>
#include "ffx_api.h"
#include "ffx_upscale.h"
#include "dx12/ffx_api_dx12.h"
#include "xess/xess.h"
#include "xess/xess_d3d12.h"
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include "nvsdk_ngx.h"
#include "nvsdk_ngx_helpers.h"
#include "jlh_upscale.h"

static char g_err[512];
static int g_which;
static ID3D11Device *g_dev;
static NVSDK_NGX_Parameter *g_params;
static NVSDK_NGX_Handle *g_dlss;
static int g_ngx_up;

static void err(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(g_err, sizeof g_err, fmt, ap);
    va_end(ap);
}

static void dll_dir(wchar_t *out, size_t n)
{
    HMODULE m = NULL;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)&dll_dir, &m);
    GetModuleFileNameW(m, out, (DWORD)n);
    wchar_t *s = wcsrchr(out, L'\\');
    if (s) s[1] = 0;
}

static int dlss_create(ID3D11Device *dev, ID3D11DeviceContext *ctx, unsigned in_w, unsigned in_h,
                       unsigned out_w, unsigned out_h)
{
    NVSDK_NGX_Result r;
    int avail = 0;
    if (!g_ngx_up) {
        wchar_t dir[MAX_PATH];
        dll_dir(dir, MAX_PATH);
        r = NVSDK_NGX_D3D11_Init_with_ProjectID("8f3b2a5c-4d1e-4a7b-9c2d-6e5f1a0b3c4d",
                                                NVSDK_NGX_ENGINE_TYPE_CUSTOM, "1.0", dir, dev);
        if (NVSDK_NGX_FAILED(r)) {
            err("NGX init failed 0x%08X (driver too old or not an RTX GPU)", (unsigned)r);
            return 0;
        }
        g_ngx_up = 1;
        g_dev = dev;
        r = NVSDK_NGX_D3D11_GetCapabilityParameters(&g_params);
        if (NVSDK_NGX_FAILED(r) || !g_params) {
            err("NGX capability parameters failed 0x%08X", (unsigned)r);
            return 0;
        }
    }
    NVSDK_NGX_Parameter_GetI(g_params, NVSDK_NGX_Parameter_SuperSampling_Available, &avail);
    if (!avail) {
        int needs = 0;
        NVSDK_NGX_Parameter_GetI(g_params, NVSDK_NGX_Parameter_SuperSampling_NeedsUpdatedDriver, &needs);
        err("DLSS not available on this GPU%s", needs ? " (driver update needed)" : "");
        return 0;
    }
    if (g_dlss) {
        NVSDK_NGX_D3D11_ReleaseFeature(g_dlss);
        g_dlss = NULL;
    }
    NVSDK_NGX_DLSS_Create_Params cp;
    memset(&cp, 0, sizeof cp);
    cp.Feature.InWidth = in_w;
    cp.Feature.InHeight = in_h;
    cp.Feature.InTargetWidth = out_w;
    cp.Feature.InTargetHeight = out_h;
    {
        double ratio = (double)out_w / (double)in_w;
        cp.Feature.InPerfQualityValue = ratio <= 1.01 ? NVSDK_NGX_PerfQuality_Value_DLAA
                                      : ratio <= 1.6 ? NVSDK_NGX_PerfQuality_Value_MaxQuality
                                      : ratio <= 1.8 ? NVSDK_NGX_PerfQuality_Value_Balanced
                                      : ratio <= 2.2 ? NVSDK_NGX_PerfQuality_Value_MaxPerf
                                                     : NVSDK_NGX_PerfQuality_Value_UltraPerformance;
    }
    cp.InFeatureCreateFlags = NVSDK_NGX_DLSS_Feature_Flags_MVLowRes
                            | NVSDK_NGX_DLSS_Feature_Flags_AutoExposure;
    r = NGX_D3D11_CREATE_DLSS_EXT(ctx, &g_dlss, g_params, &cp);
    if (NVSDK_NGX_FAILED(r) || !g_dlss) {
        err("DLSS create %ux%u -> %ux%u failed 0x%08X", in_w, in_h, out_w, out_h, (unsigned)r);
        g_dlss = NULL;
        return 0;
    }
    return 1;
}


// ---- FSR and XeSS: D3D12 beside the game's D3D11 ---------------------------
// A D3D12 device on the same adapter; shared textures (inputs copied in by
// the D3D11 context, the output copied out) and a shared fence order the two
// queues on the GPU, so nothing waits on the CPU but the allocator reuse.
struct d12_t {
    ID3D12Device *dev;
    ID3D12CommandQueue *q;
    ID3D12CommandAllocator *alloc[2];
    ID3D12GraphicsCommandList *cl;
    ID3D12Fence *fence;
    ID3D11Fence *fence11;
    ID3D11DeviceContext4 *ctx4;
    HANDLE ev;
    UINT64 fv, done[2];
    int slot;
    ID3D12Resource *r[4];           // colour, depth, motion, output
    ID3D11Texture2D *t[4];
    unsigned in_w, in_h, out_w, out_h;
};
static d12_t D;
static ffxContext g_fsr;
static int g_fsr_up;
static xess_context_handle_t g_xess;

static void d12_free_tex(void)
{
    for (int i = 0; i < 4; i++) {
        if (D.t[i]) D.t[i]->Release();
        if (D.r[i]) D.r[i]->Release();
        D.t[i] = NULL;
        D.r[i] = NULL;
    }
}

static int d12_init(ID3D11Device *dev, ID3D11DeviceContext *ctx)
{
    if (D.dev)
        return 1;
    IDXGIDevice *xd = NULL;
    IDXGIAdapter *ad = NULL;
    DXGI_ADAPTER_DESC desc;
    IDXGIFactory4 *f = NULL;
    IDXGIAdapter1 *ad12 = NULL;
    HRESULT hr;
    if (FAILED(dev->QueryInterface(__uuidof(IDXGIDevice), (void **)&xd)) || FAILED(xd->GetAdapter(&ad))) {
        err("no DXGI adapter");
        return 0;
    }
    ad->GetDesc(&desc);
    ad->Release();
    xd->Release();
    if (FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory4), (void **)&f))
        || FAILED(f->EnumAdapterByLuid(desc.AdapterLuid, __uuidof(IDXGIAdapter1), (void **)&ad12))) {
        err("adapter not found for D3D12");
        if (f) f->Release();
        return 0;
    }
    f->Release();
    hr = D3D12CreateDevice(ad12, D3D_FEATURE_LEVEL_12_0, __uuidof(ID3D12Device), (void **)&D.dev);
    ad12->Release();
    if (FAILED(hr)) {
        err("D3D12CreateDevice failed 0x%08lX", (unsigned long)hr);
        return 0;
    }
    D3D12_COMMAND_QUEUE_DESC qd = {};
    qd.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    if (FAILED(D.dev->CreateCommandQueue(&qd, __uuidof(ID3D12CommandQueue), (void **)&D.q)))
        { err("D3D12 queue failed"); return 0; }
    for (int i = 0; i < 2; i++)
        if (FAILED(D.dev->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, __uuidof(ID3D12CommandAllocator),
                                                 (void **)&D.alloc[i])))
            { err("D3D12 allocator failed"); return 0; }
    if (FAILED(D.dev->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, D.alloc[0], NULL,
                                        __uuidof(ID3D12GraphicsCommandList), (void **)&D.cl)))
        { err("D3D12 command list failed"); return 0; }
    D.cl->Close();
    if (FAILED(D.dev->CreateFence(0, D3D12_FENCE_FLAG_SHARED, __uuidof(ID3D12Fence), (void **)&D.fence)))
        { err("D3D12 fence failed"); return 0; }
    HANDLE h = NULL;
    D.dev->CreateSharedHandle(D.fence, NULL, GENERIC_ALL, NULL, &h);
    ID3D11Device5 *dev5 = NULL;
    if (!h || FAILED(dev->QueryInterface(__uuidof(ID3D11Device5), (void **)&dev5))
        || FAILED(dev5->OpenSharedFence(h, __uuidof(ID3D11Fence), (void **)&D.fence11))
        || FAILED(ctx->QueryInterface(__uuidof(ID3D11DeviceContext4), (void **)&D.ctx4))) {
        err("shared fence failed (needs Windows 10 1703+)");
        if (dev5) dev5->Release();
        if (h) CloseHandle(h);
        return 0;
    }
    dev5->Release();
    CloseHandle(h);
    D.ev = CreateEventW(NULL, FALSE, FALSE, NULL);
    return 1;
}

static int d12_tex(ID3D11Device *dev, unsigned in_w, unsigned in_h, unsigned out_w, unsigned out_h)
{
    static const DXGI_FORMAT fmt[4] = { DXGI_FORMAT_B8G8R8A8_UNORM, DXGI_FORMAT_R32_FLOAT,
                                        DXGI_FORMAT_R16G16_FLOAT, DXGI_FORMAT_R8G8B8A8_UNORM };
    ID3D11Device1 *dev1 = NULL;
    d12_free_tex();
    if (FAILED(dev->QueryInterface(__uuidof(ID3D11Device1), (void **)&dev1)))
        { err("no D3D11.1"); return 0; }
    for (int i = 0; i < 4; i++) {
        D3D12_HEAP_PROPERTIES hp = {};
        D3D12_RESOURCE_DESC rd = {};
        hp.Type = D3D12_HEAP_TYPE_DEFAULT;
        rd.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
        rd.Width = i == 3 ? out_w : in_w;
        rd.Height = i == 3 ? out_h : in_h;
        rd.DepthOrArraySize = 1;
        rd.MipLevels = 1;
        rd.Format = fmt[i];
        rd.SampleDesc.Count = 1;
        rd.Flags = D3D12_RESOURCE_FLAG_ALLOW_SIMULTANEOUS_ACCESS | D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET
                 | (i == 3 ? D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS : D3D12_RESOURCE_FLAG_NONE);
        HANDLE h = NULL;
        HRESULT h1 = D.dev->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_SHARED, &rd, D3D12_RESOURCE_STATE_COMMON,
                                                    NULL, __uuidof(ID3D12Resource), (void **)&D.r[i]);
        HRESULT h2 = SUCCEEDED(h1) ? D.dev->CreateSharedHandle(D.r[i], NULL, GENERIC_ALL, NULL, &h) : E_FAIL;
        HRESULT h3 = SUCCEEDED(h2) ? dev1->OpenSharedResource1(h, __uuidof(ID3D11Texture2D), (void **)&D.t[i]) : E_FAIL;
        if (FAILED(h1) || FAILED(h2) || FAILED(h3)) {
            err("shared texture %d failed (create 0x%08lX, handle 0x%08lX, open 0x%08lX)", i,
                (unsigned long)h1, (unsigned long)h2, (unsigned long)h3);
            if (h) CloseHandle(h);
            dev1->Release();
            d12_free_tex();
            return 0;
        }
        CloseHandle(h);
    }
    dev1->Release();
    D.in_w = in_w; D.in_h = in_h; D.out_w = out_w; D.out_h = out_h;
    return 1;
}

static void d12_wait_slot(int s)
{
    if (D.done[s] && D.fence->GetCompletedValue() < D.done[s]) {
        D.fence->SetEventOnCompletion(D.done[s], D.ev);
        WaitForSingleObject(D.ev, 1000);
    }
}

static void barrier(ID3D12Resource *r, D3D12_RESOURCE_STATES a, D3D12_RESOURCE_STATES b, D3D12_RESOURCE_BARRIER *out)
{
    memset(out, 0, sizeof *out);
    out->Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    out->Transition.pResource = r;
    out->Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    out->Transition.StateBefore = a;
    out->Transition.StateAfter = b;
}

static void fsr_destroy(void)
{
    if (g_fsr_up) {
        ffxDestroyContext(&g_fsr, NULL);
        g_fsr_up = 0;
    }
}

static int fsr_create(unsigned in_w, unsigned in_h, unsigned out_w, unsigned out_h)
{
    fsr_destroy();
    ffxCreateBackendDX12Desc be = {};
    be.header.type = FFX_API_CREATE_CONTEXT_DESC_TYPE_BACKEND_DX12;
    be.device = D.dev;
    ffxCreateContextDescUpscale cd = {};
    cd.header.type = FFX_API_CREATE_CONTEXT_DESC_TYPE_UPSCALE;
    cd.header.pNext = &be.header;
    cd.flags = FFX_UPSCALE_ENABLE_AUTO_EXPOSURE | FFX_UPSCALE_ENABLE_NON_LINEAR_COLORSPACE;
    cd.maxRenderSize.width = in_w;
    cd.maxRenderSize.height = in_h;
    cd.maxUpscaleSize.width = out_w;
    cd.maxUpscaleSize.height = out_h;
    ffxReturnCode_t rc = ffxCreateContext(&g_fsr, &cd.header, NULL);
    if (rc != FFX_API_RETURN_OK) {
        err("FSR create failed (%u): amd_fidelityfx_upscaler_dx12.dll missing or GPU unsupported", (unsigned)rc);
        return 0;
    }
    g_fsr_up = 1;
    return 1;
}

static void xess_destroy(void)
{
    if (g_xess) {
        xessDestroyContext(g_xess);
        g_xess = NULL;
    }
}

static int xess_create(unsigned in_w, unsigned in_h, unsigned out_w, unsigned out_h)
{
    xess_destroy();
    if (xessD3D12CreateContext(D.dev, &g_xess) != XESS_RESULT_SUCCESS || !g_xess) {
        err("XeSS context failed (libxess.dll missing?)");
        g_xess = NULL;
        return 0;
    }
    xess_d3d12_init_params_t ip = {};
    ip.outputResolution.x = out_w;
    ip.outputResolution.y = out_h;
    double ratio = (double)out_w / (double)in_w;
    ip.qualitySetting = ratio <= 1.01 ? XESS_QUALITY_SETTING_AA
                      : ratio <= 1.6 ? XESS_QUALITY_SETTING_QUALITY
                      : ratio <= 1.8 ? XESS_QUALITY_SETTING_BALANCED
                      : ratio <= 2.2 ? XESS_QUALITY_SETTING_PERFORMANCE
                                     : XESS_QUALITY_SETTING_ULTRA_PERFORMANCE;
    ip.initFlags = XESS_INIT_FLAG_LDR_INPUT_COLOR | XESS_INIT_FLAG_ENABLE_AUTOEXPOSURE;
    xess_result_t r = xessD3D12Init(g_xess, &ip);
    if (r != XESS_RESULT_SUCCESS) {
        err("XeSS init failed (%d)", (int)r);
        xess_destroy();
        return 0;
    }
    xessSetVelocityScale(g_xess, (float)in_w, (float)in_h);
    return 1;
}

static int d12_create(int which, ID3D11Device *dev, ID3D11DeviceContext *ctx, unsigned in_w, unsigned in_h,
                      unsigned out_w, unsigned out_h)
{
    if (!d12_init(dev, ctx) || !d12_tex(dev, in_w, in_h, out_w, out_h))
        return 0;
    return which == JLHU_FSR ? fsr_create(in_w, in_h, out_w, out_h)
                             : xess_create(in_w, in_h, out_w, out_h);
}

static int d12_evaluate(int which, ID3D11DeviceContext *ctx, const jlhu_eval *e)
{
    // D3D11: the inputs into the shared textures, then a signal
    ctx->CopyResource(D.t[0], e->color);
    ctx->CopyResource(D.t[1], e->depth);
    ctx->CopyResource(D.t[2], e->mv);
    UINT64 in_ready = ++D.fv;
    D.ctx4->Signal(D.fence11, in_ready);
    ctx->Flush();
    // D3D12: wait for them, upscale, signal
    int s = D.slot;
    d12_wait_slot(s);
    D.alloc[s]->Reset();
    D.cl->Reset(D.alloc[s], NULL);
    D3D12_RESOURCE_BARRIER b[4];
    for (int i = 0; i < 3; i++)
        barrier(D.r[i], D3D12_RESOURCE_STATE_COMMON, D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE, &b[i]);
    barrier(D.r[3], D3D12_RESOURCE_STATE_COMMON, D3D12_RESOURCE_STATE_UNORDERED_ACCESS, &b[3]);
    D.cl->ResourceBarrier(4, b);
    int ok = 1;
    if (which == JLHU_FSR) {
        ffxDispatchDescUpscale dd = {};
        dd.header.type = FFX_API_DISPATCH_DESC_TYPE_UPSCALE;
        dd.commandList = D.cl;
        dd.color = ffxApiGetResourceDX12(D.r[0], FFX_API_RESOURCE_STATE_COMPUTE_READ);
        dd.depth = ffxApiGetResourceDX12(D.r[1], FFX_API_RESOURCE_STATE_COMPUTE_READ);
        dd.motionVectors = ffxApiGetResourceDX12(D.r[2], FFX_API_RESOURCE_STATE_COMPUTE_READ);
        dd.output = ffxApiGetResourceDX12(D.r[3], FFX_API_RESOURCE_STATE_UNORDERED_ACCESS);
        dd.jitterOffset.x = e->jitter_x;
        dd.jitterOffset.y = e->jitter_y;
        dd.motionVectorScale.x = e->mv_scale_x;
        dd.motionVectorScale.y = e->mv_scale_y;
        dd.renderSize.width = e->in_w;
        dd.renderSize.height = e->in_h;
        dd.upscaleSize.width = D.out_w;
        dd.upscaleSize.height = D.out_h;
        dd.enableSharpening = true;
        dd.sharpness = 0.3f;
        dd.frameTimeDelta = e->frame_ms;
        dd.preExposure = 1.0f;
        dd.reset = e->reset != 0;
        dd.cameraNear = 1.0f;
        dd.cameraFar = 10000.0f;
        dd.cameraFovAngleVertical = 1.0f;
        dd.viewSpaceToMetersFactor = 1.0f;
        dd.flags = FFX_UPSCALE_FLAG_NON_LINEAR_COLOR_SRGB;
        ffxReturnCode_t rc = ffxDispatch(&g_fsr, &dd.header);
        if (rc != FFX_API_RETURN_OK) {
            err("FSR dispatch failed (%u)", (unsigned)rc);
            ok = 0;
        }
    } else {
        xess_d3d12_execute_params_t xp = {};
        xp.pColorTexture = D.r[0];
        xp.pVelocityTexture = D.r[2];
        xp.pDepthTexture = D.r[1];
        xp.pOutputTexture = D.r[3];
        xp.jitterOffsetX = e->jitter_x;
        xp.jitterOffsetY = e->jitter_y;
        xp.exposureScale = 1.0f;
        xp.resetHistory = e->reset ? 1 : 0;
        xp.inputWidth = e->in_w;
        xp.inputHeight = e->in_h;
        xess_result_t r = xessD3D12Execute(g_xess, D.cl, &xp);
        if (r != XESS_RESULT_SUCCESS) {
            err("XeSS execute failed (%d)", (int)r);
            ok = 0;
        }
    }
    for (int i = 0; i < 3; i++)
        barrier(D.r[i], D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE, D3D12_RESOURCE_STATE_COMMON, &b[i]);
    barrier(D.r[3], D3D12_RESOURCE_STATE_UNORDERED_ACCESS, D3D12_RESOURCE_STATE_COMMON, &b[3]);
    D.cl->ResourceBarrier(4, b);
    D.cl->Close();
    D.q->Wait(D.fence, in_ready);
    ID3D12CommandList *lists[1] = { D.cl };
    D.q->ExecuteCommandLists(1, lists);
    UINT64 out_ready = ++D.fv;
    D.q->Signal(D.fence, out_ready);
    D.done[s] = out_ready;
    D.slot ^= 1;
    // D3D11: wait on the GPU, then the result out
    D.ctx4->Wait(D.fence11, out_ready);
    if (ok)
        ctx->CopyResource(e->out, D.t[3]);
    return ok;
}

static void d12_destroy(void)
{
    if (D.q && D.fence) {
        UINT64 v = ++D.fv;
        D.q->Signal(D.fence, v);
        D.fence->SetEventOnCompletion(v, D.ev);
        WaitForSingleObject(D.ev, 2000);
    }
    fsr_destroy();
    xess_destroy();
    d12_free_tex();
}

extern "C" __declspec(dllexport) int jlhu_create(int which, ID3D11Device *dev, ID3D11DeviceContext *ctx,
                                                 unsigned in_w, unsigned in_h, unsigned out_w,
                                                 unsigned out_h)
{
    g_err[0] = 0;
    g_which = 0;
    if (which == JLHU_DLSS) {
        if (!dlss_create(dev, ctx, in_w, in_h, out_w, out_h))
            return 0;
        g_which = which;
        return 1;
    }
    if (which == JLHU_FSR || which == JLHU_XESS) {
        if (!d12_create(which, dev, ctx, in_w, in_h, out_w, out_h))
            return 0;
        g_which = which;
        return 1;
    }
    err("unknown upscaler %d", which);
    return 0;
}

extern "C" __declspec(dllexport) int jlhu_evaluate(ID3D11DeviceContext *ctx, const jlhu_eval *e)
{
    if (g_which == JLHU_DLSS && g_dlss) {
        NVSDK_NGX_D3D11_DLSS_Eval_Params ep;
        memset(&ep, 0, sizeof ep);
        ep.Feature.pInColor = e->color;
        ep.Feature.pInOutput = e->out;
        ep.pInDepth = e->depth;
        ep.pInMotionVectors = e->mv;
        ep.InJitterOffsetX = e->jitter_x;
        ep.InJitterOffsetY = e->jitter_y;
        ep.InRenderSubrectDimensions.Width = e->in_w;
        ep.InRenderSubrectDimensions.Height = e->in_h;
        ep.InReset = e->reset;
        ep.InMVScaleX = e->mv_scale_x;
        ep.InMVScaleY = e->mv_scale_y;
        ep.InFrameTimeDeltaInMsec = e->frame_ms;
        NVSDK_NGX_Result r = NGX_D3D11_EVALUATE_DLSS_EXT(ctx, g_dlss, g_params, &ep);
        if (NVSDK_NGX_FAILED(r)) {
            err("DLSS evaluate failed 0x%08X", (unsigned)r);
            return 0;
        }
        return 1;
    }
    if ((g_which == JLHU_FSR || g_which == JLHU_XESS) && D.dev)
        return d12_evaluate(g_which, ctx, e);
    return 0;
}

extern "C" __declspec(dllexport) void jlhu_destroy(void)
{
    d12_destroy();
    if (g_dlss) {
        NVSDK_NGX_D3D11_ReleaseFeature(g_dlss);
        g_dlss = NULL;
    }
    if (g_params) {
        NVSDK_NGX_D3D11_DestroyParameters(g_params);
        g_params = NULL;
    }
    if (g_ngx_up && g_dev)
        NVSDK_NGX_D3D11_Shutdown1(g_dev);
    g_ngx_up = 0;
    g_which = 0;
}

extern "C" __declspec(dllexport) const char *jlhu_error(void)
{
    return g_err;
}
