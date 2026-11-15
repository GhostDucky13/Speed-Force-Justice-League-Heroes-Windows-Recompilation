/*
 * sfui.h - the small immediate-mode UI shared by the Speed Force builder and launcher.
 *
 * Everything is painted by the program (GDI+ for anti-aliased shapes, GDI ClearType text) into
 * a back buffer; buttons, checkboxes, selectors and links register their rectangles while they
 * are painted and the window procedure hit-tests them. Text input uses real EDIT controls,
 * coloured dark. Coordinates are logical (96 DPI) and scaled with S().
 */
#ifndef SFUI_H
#define SFUI_H

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#include <windows.h>
#include <windowsx.h>
#include <dwmapi.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

/* ---------------------------------------------------------------- colours */
#define RGBA(r, g, b, a) ((DWORD)(((DWORD)(a) << 24) | ((DWORD)(r) << 16) | ((DWORD)(g) << 8) | (DWORD)(b)))
#define C_BG       RGBA(10, 14, 28, 255)
#define C_BG2      RGBA(14, 19, 38, 255)
#define C_CARD     RGBA(20, 27, 48, 255)
#define C_CARD2    RGBA(26, 34, 60, 255)
#define C_BORDER   RGBA(38, 48, 78, 255)
#define C_INPUT    RGBA(12, 17, 33, 255)
#define C_TEXT     RGBA(236, 240, 250, 255)
#define C_SUB      RGBA(140, 152, 182, 255)
#define C_DIM      RGBA(92, 104, 134, 255)
#define C_ACCENT   RGBA(255, 196, 40, 255)
#define C_ACCENT2  RGBA(255, 140, 30, 255)
#define C_ACCENTHI RGBA(255, 214, 92, 255)
#define C_OK       RGBA(58, 210, 159, 255)
#define C_BAD      RGBA(255, 92, 92, 255)
#define C_BLUE     RGBA(90, 160, 255, 255)
#define C_HOVER    RGBA(34, 44, 76, 255)

static COLORREF ui_cr(DWORD c) { return RGB((c >> 16) & 255, (c >> 8) & 255, c & 255); }

/* ---------------------------------------------------------------- GDI+ (flat API, declared here) */
typedef int GpStatus;
typedef void GpGraphics, GpBrush, GpPath, GpPen, GpImage;
typedef struct { UINT32 GdiplusVersion; void *DebugEventCallback; BOOL SuppressBackgroundThread; BOOL SuppressExternalCodecs; } GpStartupInput;
GpStatus WINAPI GdiplusStartup(ULONG_PTR *, const GpStartupInput *, void *);
GpStatus WINAPI GdipCreateFromHDC(HDC, GpGraphics **);
GpStatus WINAPI GdipDeleteGraphics(GpGraphics *);
GpStatus WINAPI GdipSetSmoothingMode(GpGraphics *, int);
GpStatus WINAPI GdipSetInterpolationMode(GpGraphics *, int);
GpStatus WINAPI GdipSetPixelOffsetMode(GpGraphics *, int);
GpStatus WINAPI GdipCreateSolidFill(DWORD, GpBrush **);
GpStatus WINAPI GdipCreateLineBrushI(const POINT *, const POINT *, DWORD, DWORD, int, GpBrush **);
GpStatus WINAPI GdipDeleteBrush(GpBrush *);
GpStatus WINAPI GdipCreatePen1(DWORD, float, int, GpPen **);
GpStatus WINAPI GdipSetPenStartCap(GpPen *, int);
GpStatus WINAPI GdipSetPenEndCap(GpPen *, int);
GpStatus WINAPI GdipSetPenLineJoin(GpPen *, int);
GpStatus WINAPI GdipDeletePen(GpPen *);
GpStatus WINAPI GdipCreatePath(int, GpPath **);
GpStatus WINAPI GdipDeletePath(GpPath *);
GpStatus WINAPI GdipAddPathArc(GpPath *, float, float, float, float, float, float);
GpStatus WINAPI GdipAddPathLine(GpPath *, float, float, float, float);
GpStatus WINAPI GdipClosePathFigure(GpPath *);
GpStatus WINAPI GdipFillPath(GpGraphics *, GpBrush *, GpPath *);
GpStatus WINAPI GdipDrawPath(GpGraphics *, GpPen *, GpPath *);
GpStatus WINAPI GdipFillEllipse(GpGraphics *, GpBrush *, float, float, float, float);
GpStatus WINAPI GdipDrawEllipse(GpGraphics *, GpPen *, float, float, float, float);
GpStatus WINAPI GdipDrawArc(GpGraphics *, GpPen *, float, float, float, float, float, float);
GpStatus WINAPI GdipDrawLine(GpGraphics *, GpPen *, float, float, float, float);
GpStatus WINAPI GdipFillRectangle(GpGraphics *, GpBrush *, float, float, float, float);
GpStatus WINAPI GdipCreateBitmapFromStream(IStream *, GpImage **);
GpStatus WINAPI GdipDrawImageRectI(GpGraphics *, GpImage *, INT, INT, INT, INT);
GpStatus WINAPI GdipGetImageWidth(GpImage *, UINT *);
GpStatus WINAPI GdipGetImageHeight(GpImage *, UINT *);
GpStatus WINAPI GdipDisposeImage(GpImage *);
GpStatus WINAPI GdipFlush(GpGraphics *, int);

/* ---------------------------------------------------------------- state */
typedef struct { RECT r; int id; int kind; } UiHit;
enum { UI_BUTTON = 1, UI_CHECK, UI_LINK, UI_PREV, UI_NEXT, UI_NAV, UI_SLIDER };

static struct {
    HWND wnd;
    int dpi;
    HDC dc;                      /* the back buffer while painting */
    GpGraphics *g;
    UiHit hits[160];
    int nhits;
    int hot, down;
    HFONT f_title, f_h1, f_h2, f_body, f_bold, f_small, f_mono, f_big, f_huge;
    ULONG_PTR gdiplus;
    HBRUSH input_brush;
} ui;

static int S(int v) { return MulDiv(v, ui.dpi, 96); }
static float SF(float v) { return v * (float)ui.dpi / 96.0f; }

static HFONT ui_font(int px, int weight, const wchar_t *face)
{
    return CreateFontW(-S(px), 0, 0, 0, weight, 0, 0, 0, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                       CLEARTYPE_QUALITY, DEFAULT_PITCH, face);
}

static void ui_fonts(void)
{
    HFONT *all[] = {&ui.f_title, &ui.f_h1, &ui.f_h2, &ui.f_body, &ui.f_bold, &ui.f_small, &ui.f_mono, &ui.f_big, &ui.f_huge};
    size_t i;
    for (i = 0; i < sizeof all / sizeof all[0]; i++)
        if (*all[i])
            DeleteObject(*all[i]);
    ui.f_title = ui_font(28, FW_SEMIBOLD, L"Segoe UI");
    ui.f_h1 = ui_font(22, FW_SEMIBOLD, L"Segoe UI");
    ui.f_h2 = ui_font(16, FW_SEMIBOLD, L"Segoe UI");
    ui.f_body = ui_font(14, FW_NORMAL, L"Segoe UI");
    ui.f_bold = ui_font(14, FW_SEMIBOLD, L"Segoe UI");
    ui.f_small = ui_font(12, FW_NORMAL, L"Segoe UI");
    ui.f_mono = ui_font(12, FW_NORMAL, L"Consolas");
    ui.f_big = ui_font(20, FW_BOLD, L"Segoe UI");
    ui.f_huge = ui_font(40, FW_BOLD, L"Segoe UI");
}

static void ui_init(HWND w)
{
    GpStartupInput in = {1, NULL, FALSE, FALSE};
    ui.wnd = w;
    ui.dpi = (int)GetDpiForWindow(w);
    if (ui.dpi <= 0)
        ui.dpi = 96;
    if (!ui.gdiplus)
        GdiplusStartup(&ui.gdiplus, &in, NULL);
    ui_fonts();
    if (!ui.input_brush)
        ui.input_brush = CreateSolidBrush(ui_cr(C_INPUT));
    {
        BOOL dark = TRUE;
        COLORREF cap = ui_cr(C_BG), txt = ui_cr(C_TEXT);
        DwmSetWindowAttribute(w, 20, &dark, sizeof dark);      /* DWMWA_USE_IMMERSIVE_DARK_MODE */
        DwmSetWindowAttribute(w, 35, &cap, sizeof cap);        /* DWMWA_CAPTION_COLOR (Windows 11) */
        DwmSetWindowAttribute(w, 36, &txt, sizeof txt);        /* DWMWA_TEXT_COLOR */
    }
}

/* ---------------------------------------------------------------- shapes */
static GpPath *ui_round_path(float x, float y, float w, float h, float r)
{
    GpPath *p;
    float d = r * 2;
    GdipCreatePath(0, &p);
    if (r <= 0.5f) {
        GdipAddPathLine(p, x, y, x + w, y);
        GdipAddPathLine(p, x + w, y, x + w, y + h);
        GdipAddPathLine(p, x + w, y + h, x, y + h);
    } else {
        if (d > h) d = h;
        if (d > w) d = w;
        GdipAddPathArc(p, x, y, d, d, 180, 90);
        GdipAddPathArc(p, x + w - d, y, d, d, 270, 90);
        GdipAddPathArc(p, x + w - d, y + h - d, d, d, 0, 90);
        GdipAddPathArc(p, x, y + h - d, d, d, 90, 90);
    }
    GdipClosePathFigure(p);
    return p;
}

static void ui_round(RECT r, int radius, DWORD fill, DWORD border)
{
    GpPath *p = ui_round_path((float)r.left + 0.5f, (float)r.top + 0.5f, (float)(r.right - r.left - 1),
                              (float)(r.bottom - r.top - 1), SF((float)radius));
    if (fill >> 24) {
        GpBrush *b;
        GdipCreateSolidFill(fill, &b);
        GdipFillPath(ui.g, b, p);
        GdipDeleteBrush(b);
    }
    if (border >> 24) {
        GpPen *pen;
        GdipCreatePen1(border, SF(1.0f), 2, &pen);
        GdipDrawPath(ui.g, pen, p);
        GdipDeletePen(pen);
    }
    GdipDeletePath(p);
}

static void ui_round_grad(RECT r, int radius, DWORD c0, DWORD c1)
{
    POINT a = {r.left, r.top}, b = {r.right, r.top};
    GpBrush *br;
    GpPath *p = ui_round_path((float)r.left, (float)r.top, (float)(r.right - r.left), (float)(r.bottom - r.top),
                              SF((float)radius));
    GdipCreateLineBrushI(&a, &b, c0, c1, 0, &br);
    GdipFillPath(ui.g, br, p);
    GdipDeleteBrush(br);
    GdipDeletePath(p);
}

static void ui_circle(float cx, float cy, float rad, DWORD fill, DWORD ring, float ring_w)
{
    if (fill >> 24) {
        GpBrush *b;
        GdipCreateSolidFill(fill, &b);
        GdipFillEllipse(ui.g, b, cx - rad, cy - rad, rad * 2, rad * 2);
        GdipDeleteBrush(b);
    }
    if (ring >> 24) {
        GpPen *p;
        GdipCreatePen1(ring, ring_w, 2, &p);
        GdipDrawEllipse(ui.g, p, cx - rad, cy - rad, rad * 2, rad * 2);
        GdipDeletePen(p);
    }
}

static void ui_line(float x0, float y0, float x1, float y1, DWORD c, float w)
{
    GpPen *p;
    GdipCreatePen1(c, w, 2, &p);
    GdipSetPenStartCap(p, 2);
    GdipSetPenEndCap(p, 2);
    GdipDrawLine(ui.g, p, x0, y0, x1, y1);
    GdipDeletePen(p);
}

/* status glyphs: 1 done, 2 running (spinner phase), 3 failed, 0 waiting */
static void ui_status_icon(int cx, int cy, int state, int phase)
{
    float x = (float)cx, y = (float)cy, r = SF(10);
    if (state == 1) {
        ui_circle(x, y, r, RGBA(58, 210, 159, 40), C_OK, SF(1.6f));
        ui_line(x - SF(4.5f), y + SF(0.2f), x - SF(1.2f), y + SF(3.5f), C_OK, SF(2));
        ui_line(x - SF(1.2f), y + SF(3.5f), x + SF(5), y - SF(3.5f), C_OK, SF(2));
    } else if (state == 2) {
        GpPen *p;
        ui_circle(x, y, r, 0, RGBA(255, 196, 40, 50), SF(2.2f));
        GdipCreatePen1(C_ACCENT, SF(2.4f), 2, &p);
        GdipSetPenStartCap(p, 2);
        GdipSetPenEndCap(p, 2);
        GdipDrawArc(ui.g, p, x - r, y - r, r * 2, r * 2, (float)(phase % 360), 110);
        GdipDeletePen(p);
    } else if (state == 3) {
        ui_circle(x, y, r, RGBA(255, 92, 92, 40), C_BAD, SF(1.6f));
        ui_line(x - SF(4), y - SF(4), x + SF(4), y + SF(4), C_BAD, SF(2));
        ui_line(x + SF(4), y - SF(4), x - SF(4), y + SF(4), C_BAD, SF(2));
    } else if (state == 4) {           /* warning */
        ui_circle(x, y, r, RGBA(255, 196, 40, 40), C_ACCENT, SF(1.6f));
        ui_line(x, y - SF(4.5f), x, y + SF(1), C_ACCENT, SF(2));
        ui_circle(x, y + SF(4.5f), SF(1.3f), C_ACCENT, 0, 0);
    } else {
        ui_circle(x, y, r, 0, C_BORDER, SF(1.6f));
    }
}

/* ---------------------------------------------------------------- text */
static void ui_text(RECT r, const wchar_t *t, HFONT f, DWORD c, UINT flags)
{
    GdipFlush(ui.g, 1);
    SelectObject(ui.dc, f);
    SetTextColor(ui.dc, ui_cr(c));
    SetBkMode(ui.dc, TRANSPARENT);
    DrawTextW(ui.dc, t, -1, &r, flags | DT_NOPREFIX);
}

static int ui_text_h(int width, const wchar_t *t, HFONT f)
{
    RECT r = {0, 0, width, 0};
    SelectObject(ui.dc, f);
    DrawTextW(ui.dc, t, -1, &r, DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX);
    return r.bottom;
}

static int ui_text_w(const wchar_t *t, HFONT f)
{
    SIZE s;
    SelectObject(ui.dc, f);
    GetTextExtentPoint32W(ui.dc, t, (int)wcslen(t), &s);
    return s.cx;
}

static RECT R(int x, int y, int w, int h)
{
    RECT r = {S(x), S(y), S(x + w), S(y + h)};
    return r;
}

/* ---------------------------------------------------------------- widgets */
static void ui_hit(RECT r, int id, int kind)
{
    if (ui.nhits < (int)(sizeof ui.hits / sizeof ui.hits[0])) {
        ui.hits[ui.nhits].r = r;
        ui.hits[ui.nhits].id = id;
        ui.hits[ui.nhits].kind = kind;
        ui.nhits++;
    }
}

/* style: 0 secondary, 1 primary (gold), 2 ghost, 3 danger */
static void ui_button(RECT r, int id, const wchar_t *t, int style, int enabled)
{
    int hot = enabled && ui.hot == id;
    DWORD fill, border = 0, tc = C_TEXT;
    if (style == 1) {
        fill = enabled ? (hot ? C_ACCENTHI : C_ACCENT) : RGBA(70, 64, 40, 255);
        tc = enabled ? RGBA(18, 20, 30, 255) : C_DIM;
    } else if (style == 2) {
        fill = hot ? C_HOVER : 0;
        tc = enabled ? C_SUB : C_DIM;
        if (hot) tc = C_TEXT;
    } else if (style == 3) {
        fill = hot ? RGBA(120, 40, 48, 255) : RGBA(70, 28, 36, 255);
        border = RGBA(140, 52, 60, 255);
    } else {
        fill = hot ? C_HOVER : C_CARD2;
        border = C_BORDER;
        if (!enabled) tc = C_DIM;
    }
    if (enabled && ui.down == id && hot)
        r.top += S(1), r.bottom += S(1);
    ui_round(r, 8, fill, border);
    ui_text(r, t, ui.f_bold, tc, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    if (enabled)
        ui_hit(r, id, UI_BUTTON);
}

static void ui_check(RECT r, int id, const wchar_t *t, int on)
{
    int box = S(20), y = r.top + (r.bottom - r.top - box) / 2;
    RECT b = {r.left, y, r.left + box, y + box}, tr = r;
    ui_round(b, 5, on ? C_ACCENT : C_INPUT, on ? 0 : (ui.hot == id ? C_SUB : C_BORDER));
    if (on) {
        float x = (float)b.left, yy = (float)b.top;
        ui_line(x + SF(5), yy + SF(10.5f), x + SF(8.5f), yy + SF(14), RGBA(18, 20, 30, 255), SF(2.2f));
        ui_line(x + SF(8.5f), yy + SF(14), x + SF(15), yy + SF(6.5f), RGBA(18, 20, 30, 255), SF(2.2f));
    }
    tr.left += box + S(10);
    ui_text(tr, t, ui.f_body, C_TEXT, DT_VCENTER | DT_SINGLELINE);
    ui_hit(r, id, UI_CHECK);
}

static void ui_link(RECT r, int id, const wchar_t *t)
{
    ui_text(r, t, ui.f_body, ui.hot == id ? C_ACCENTHI : C_SUB, DT_VCENTER | DT_SINGLELINE);
    ui_hit(r, id, UI_LINK);
}

static void ui_progress(RECT r, double frac, DWORD c0, DWORD c1)
{
    RECT f = r;
    ui_round(r, 4, C_CARD2, 0);
    if (frac > 0) {
        if (frac > 1) frac = 1;
        f.right = f.left + (LONG)((r.right - r.left) * frac);
        if (f.right - f.left < S(8)) f.right = f.left + S(8);
        ui_round_grad(f, 4, c0, c1);
    }
}

static int ui_hit_test(int x, int y, int *kind)
{
    int i;
    POINT p = {x, y};
    for (i = ui.nhits - 1; i >= 0; i--)
        if (PtInRect(&ui.hits[i].r, p)) {
            if (kind) *kind = ui.hits[i].kind;
            return ui.hits[i].id;
        }
    return 0;
}

/* Start a paint into a back buffer; returns the memory DC. */
typedef struct { HDC wdc, mdc; HBITMAP bmp, old; PAINTSTRUCT ps; RECT rc; } UiPaint;

static void ui_begin(UiPaint *p)
{
    p->wdc = BeginPaint(ui.wnd, &p->ps);
    GetClientRect(ui.wnd, &p->rc);
    p->mdc = CreateCompatibleDC(p->wdc);
    p->bmp = CreateCompatibleBitmap(p->wdc, p->rc.right, p->rc.bottom);
    p->old = (HBITMAP)SelectObject(p->mdc, p->bmp);
    ui.dc = p->mdc;
    GdipCreateFromHDC(p->mdc, &ui.g);
    GdipSetSmoothingMode(ui.g, 4);
    GdipSetInterpolationMode(ui.g, 7);
    GdipSetPixelOffsetMode(ui.g, 4);
    ui.nhits = 0;
    {
        HBRUSH b = CreateSolidBrush(ui_cr(C_BG));
        FillRect(p->mdc, &p->rc, b);
        DeleteObject(b);
    }
}

static void ui_end(UiPaint *p)
{
    GdipDeleteGraphics(ui.g);
    ui.g = NULL;
    BitBlt(p->wdc, 0, 0, p->rc.right, p->rc.bottom, p->mdc, 0, 0, SRCCOPY);
    SelectObject(p->mdc, p->old);
    DeleteObject(p->bmp);
    DeleteDC(p->mdc);
    ui.dc = NULL;
    EndPaint(ui.wnd, &p->ps);
}

/* A PNG from the program's resources (RCDATA). */
static GpImage *ui_png(int id)
{
    HRSRC r = FindResourceW(NULL, MAKEINTRESOURCEW(id), MAKEINTRESOURCEW(10));
    HGLOBAL h, mem;
    DWORD n;
    IStream *st = NULL;
    GpImage *img = NULL;
    if (!r) return NULL;
    h = LoadResource(NULL, r);
    n = SizeofResource(NULL, r);
    mem = GlobalAlloc(GMEM_MOVEABLE, n);
    memcpy(GlobalLock(mem), LockResource(h), n);
    GlobalUnlock(mem);
    if (CreateStreamOnHGlobal(mem, TRUE, &st) == S_OK) {
        GdipCreateBitmapFromStream(st, &img);
        st->lpVtbl->Release(st);
    }
    return img;
}

static void ui_image(GpImage *img, RECT r)
{
    if (img)
        GdipDrawImageRectI(ui.g, img, r.left, r.top, r.right - r.left, r.bottom - r.top);
}

/* Mouse handling shared by both programs: returns the id clicked (on button up), else 0. */
static int ui_mouse(UINT m, LPARAM lp, int *kind)
{
    int x = GET_X_LPARAM(lp), y = GET_Y_LPARAM(lp), k = 0;
    int id = ui_hit_test(x, y, &k);
    if (m == WM_MOUSEMOVE) {
        if (id != ui.hot) {
            ui.hot = id;
            InvalidateRect(ui.wnd, NULL, FALSE);
            if (id) {
                TRACKMOUSEEVENT t = {sizeof t, TME_LEAVE, ui.wnd, 0};
                TrackMouseEvent(&t);
            }
        }
        SetCursor(LoadCursor(NULL, id ? IDC_HAND : IDC_ARROW));
        return 0;
    }
    if (m == WM_MOUSELEAVE) {
        ui.hot = 0;
        InvalidateRect(ui.wnd, NULL, FALSE);
        return 0;
    }
    if (m == WM_LBUTTONDOWN) {
        ui.down = id;
        SetCapture(ui.wnd);
        InvalidateRect(ui.wnd, NULL, FALSE);
        return 0;
    }
    if (m == WM_LBUTTONUP) {
        int was = ui.down;
        ui.down = 0;
        ReleaseCapture();
        InvalidateRect(ui.wnd, NULL, FALSE);
        if (was && was == id) {
            if (kind) *kind = k;
            return id;
        }
    }
    return 0;
}

/* A dark single-line EDIT. */
static HWND ui_edit(int id)
{
    HWND e = CreateWindowExW(0, L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL | WS_TABSTOP, 0, 0, 10, 10,
                             ui.wnd, (HMENU)(INT_PTR)id, GetModuleHandleW(NULL), NULL);
    SendMessageW(e, WM_SETFONT, (WPARAM)ui.f_body, TRUE);
    return e;
}

/* Place an EDIT inside a drawn input box (the box is painted by ui_input_box). */
static void ui_place_edit(HWND e, RECT box)
{
    int h = S(20);
    SetWindowPos(e, NULL, box.left + S(12), box.top + (box.bottom - box.top - h) / 2, box.right - box.left - S(24), h,
                 SWP_NOZORDER | SWP_NOACTIVATE);
}

static void ui_input_box(RECT box, int focused)
{
    ui_round(box, 8, C_INPUT, focused ? C_ACCENT : C_BORDER);
}

/* Folder / file pickers (the modern Windows dialog). */
#include <shobjidl.h>
static int ui_pick(wchar_t *path, int folder, const wchar_t *title, const wchar_t *filter_name, const wchar_t *filter)
{
    IFileOpenDialog *d = NULL;
    int ok = 0;
    if (FAILED(CoCreateInstance(&CLSID_FileOpenDialog, NULL, CLSCTX_INPROC_SERVER, &IID_IFileOpenDialog, (void **)&d)))
        return 0;
    {
        FILEOPENDIALOGOPTIONS o;
        d->lpVtbl->GetOptions(d, &o);
        d->lpVtbl->SetOptions(d, o | FOS_FORCEFILESYSTEM | (folder ? FOS_PICKFOLDERS : FOS_FILEMUSTEXIST));
    }
    d->lpVtbl->SetTitle(d, title);
    if (!folder && filter) {
        COMDLG_FILTERSPEC f[2] = {{filter_name, filter}, {L"All files", L"*.*"}};
        d->lpVtbl->SetFileTypes(d, 2, f);
    }
    if (SUCCEEDED(d->lpVtbl->Show(d, ui.wnd))) {
        IShellItem *it = NULL;
        if (SUCCEEDED(d->lpVtbl->GetResult(d, &it))) {
            wchar_t *p = NULL;
            if (SUCCEEDED(it->lpVtbl->GetDisplayName(it, SIGDN_FILESYSPATH, &p))) {
                wcsncpy(path, p, MAX_PATH - 1);
                path[MAX_PATH - 1] = 0;
                CoTaskMemFree(p);
                ok = 1;
            }
            it->lpVtbl->Release(it);
        }
    }
    d->lpVtbl->Release(d);
    return ok;
}

static void ui_fmt_time(wchar_t *out, size_t n, double secs)
{
    int s = (int)(secs + 0.5);
    if (s >= 3600)
        swprintf(out, n, L"%d:%02d:%02d", s / 3600, (s / 60) % 60, s % 60);
    else
        swprintf(out, n, L"%d:%02d", s / 60, s % 60);
}

#endif
