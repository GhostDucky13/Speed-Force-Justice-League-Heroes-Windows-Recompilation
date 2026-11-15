/*
 * sflauncher.c - SpeedForceLauncher.exe: Play, the main F10 settings (config\config.toml, the file the
 * in-game F10 menu reads and writes), the save slots and Xbox save import, the update check
 * (the latest GitHub release of SF_GITHUB_REPO) and uninstalling ("/uninstall").
 * SpeedForce.exe, the game, also runs on its own.
 *
 * Build: windres sflauncher.rc -O coff -o sflauncher.res
 *        clang -O2 -municode -mwindows sflauncher.c sflauncher.res -lgdiplus -ldwmapi -lole32 -luuid
 *              -lshell32 -lwinhttp -o SpeedForceLauncher.exe
 */
#include "sfui.h"
#include <shlobj.h>
#include <shellapi.h>
#include <winhttp.h>

#ifndef SF_VERSION
#define SF_VERSION "2.0.0"
#endif
#ifndef SF_GITHUB_REPO
#define SF_GITHUB_REPO "ghostDucky13/Speed-Force"
#endif
#define SF_WIDEN2(x) L##x
#define SF_WIDEN(x) SF_WIDEN2(x)
#define SF_VERSION_W SF_WIDEN(SF_VERSION)
#define SF_GITHUB_REPO_W SF_WIDEN(SF_GITHUB_REPO)
#define WM_APP_DONE (WM_APP + 2)
#define WM_APP_UPDATE (WM_APP + 3)

static wchar_t g_dir[MAX_PATH];           /* the install folder (this exe's) */
static HWND g_wnd;
static wchar_t g_update_url[512];
enum { ID_SCALE = 1, ID_OUTPUT, ID_FULL, ID_SF, ID_UPS, ID_AA, ID_ANISO, ID_GLYPHS, ID_STATS };

/* ---------------------------------------------------------------- settings */
typedef struct { const char *key; const char *const *vals; const wchar_t *const *labels; int quoted; int ctl; const char *def; } Choice;
static const char *const v_scale[] = {"1", "2", "3", "4", NULL};
static const wchar_t *const l_scale[] = {L"1x (720p)", L"2x (1440p)", L"3x (2160p)", L"4x (2880p)", NULL};
static const char *const v_out[] = {"native", "1080", "1440", "2160", NULL};
static const wchar_t *const l_out[] = {L"Native (screen)", L"1080p", L"1440p", L"4K", NULL};
static const char *const v_full[] = {"true", "false", NULL};
static const wchar_t *const l_full[] = {L"Fullscreen", L"Window", NULL};
static const char *const v_sf[] = {"60", "120", "144", "240", "monitor", NULL};
static const wchar_t *const l_sf[] = {L"Off (60, original)", L"120", L"144", L"240", L"Match monitor", NULL};
static const char *const v_ups[] = {"off", "dlss", "fsr", "xess", NULL};
static const wchar_t *const l_ups[] = {L"Off", L"NVIDIA DLSS", L"AMD FSR", L"Intel XeSS", NULL};
static const char *const v_aa[] = {"off", "fxaa", "fxaa_high", "taa", NULL};
static const wchar_t *const l_aa[] = {L"Off", L"FXAA", L"FXAA (high)", L"TAA", NULL};
static const char *const v_aniso[] = {"1", "2", "4", "8", "16", NULL};
static const wchar_t *const l_aniso[] = {L"Off", L"2x", L"4x", L"8x", L"16x", NULL};
static const char *const v_glyph[] = {"auto", "xbox", "playstation", "nintendo", "gamecube", NULL};
static const wchar_t *const l_glyph[] = {L"Automatic", L"Xbox", L"PlayStation", L"Nintendo", L"GameCube", NULL};
static const char *const v_stats[] = {"false", "true", NULL};
static const wchar_t *const l_stats[] = {L"Hidden", L"Shown", NULL};

static Choice g_choices[] = {
    {"render.scale", v_scale, l_scale, 0, ID_SCALE, "4"},
    {"display.output", v_out, l_out, 1, ID_OUTPUT, "native"},
    {"present.fullscreen", v_full, l_full, 0, ID_FULL, "true"},
    {"frame.rate", v_sf, l_sf, 1, ID_SF, "monitor"},
    {"upscale.mode", v_ups, l_ups, 1, ID_UPS, "off"},
    {"render.aa", v_aa, l_aa, 1, ID_AA, "off"},
    {"render.aniso", v_aniso, l_aniso, 0, ID_ANISO, "16"},
    {"input.glyphs", v_glyph, l_glyph, 1, ID_GLYPHS, "auto"},
    {"overlay.stats", v_stats, l_stats, 0, ID_STATS, "false"},
};
#define NCHOICES (sizeof g_choices / sizeof g_choices[0])

/* config.toml as lines; only "key = value" lines inside [section]s are touched */
static char *g_cfg[2048];
static int g_ncfg;

static void cfg_path(wchar_t *out)
{
    swprintf(out, MAX_PATH, L"%ls\\config\\config.toml", g_dir);
}

static void cfg_load(void)
{
    wchar_t p[MAX_PATH];
    FILE *f;
    char line[1024];
    int i;
    for (i = 0; i < g_ncfg; i++)
        free(g_cfg[i]);
    g_ncfg = 0;
    cfg_path(p);
    f = _wfopen(p, L"rb");
    if (!f)
        return;
    while (g_ncfg < 2048 && fgets(line, sizeof line, f)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r'))
            line[--n] = 0;
        g_cfg[g_ncfg++] = _strdup(line);
    }
    fclose(f);
}

static int cfg_find(const char *sec, const char *key, int *sec_line)
{
    char cur[128] = "";
    int i;
    *sec_line = -1;
    for (i = 0; i < g_ncfg; i++) {
        const char *l = g_cfg[i];
        while (*l == ' ' || *l == '\t')
            l++;
        if (*l == '[') {
            const char *e = strchr(l, ']');
            size_t n = e ? (size_t)(e - l - 1) : 0;
            if (n >= sizeof cur)
                n = sizeof cur - 1;
            memcpy(cur, l + 1, n);
            cur[n] = 0;
            if (!strcmp(cur, sec))
                *sec_line = i;
            continue;
        }
        if (!strcmp(cur, sec)) {
            size_t kl = strlen(key);
            if (!strncmp(l, key, kl) && (l[kl] == ' ' || l[kl] == '=' || l[kl] == '\t'))
                return i;
        }
    }
    return -1;
}

static void split_key(const char *full, char *sec, char *key)
{
    const char *d = strchr(full, '.');
    memcpy(sec, full, (size_t)(d - full));
    sec[d - full] = 0;
    strcpy(key, d + 1);
}

static int cfg_get(const char *full, char *out, size_t n)
{
    char sec[64], key[64];
    int sl, i;
    split_key(full, sec, key);
    i = cfg_find(sec, key, &sl);
    if (i < 0)
        return 0;
    {
        const char *v = strchr(g_cfg[i], '=');
        size_t k;
        if (!v)
            return 0;
        v++;
        while (*v == ' ' || *v == '"')
            v++;
        for (k = 0; k + 1 < n && v[k] && v[k] != '"' && v[k] != ' ' && v[k] != '#'; k++)
            out[k] = v[k];
        out[k] = 0;
    }
    return 1;
}

static void cfg_set(const char *full, const char *val, int quoted)
{
    char sec[64], key[64], line[256];
    int sl, i;
    split_key(full, sec, key);
    snprintf(line, sizeof line, quoted ? "%s = \"%s\"" : "%s = %s", key, val);
    i = cfg_find(sec, key, &sl);
    if (i >= 0) {
        free(g_cfg[i]);
        g_cfg[i] = _strdup(line);
        return;
    }
    if (g_ncfg + 2 >= 2048)
        return;
    if (sl < 0) {
        char h[80];
        snprintf(h, sizeof h, "[%s]", sec);
        g_cfg[g_ncfg++] = _strdup(h);
        g_cfg[g_ncfg++] = _strdup(line);
        return;
    }
    memmove(&g_cfg[sl + 2], &g_cfg[sl + 1], sizeof(char *) * (size_t)(g_ncfg - sl - 1));
    g_cfg[sl + 1] = _strdup(line);
    g_ncfg++;
}

static int cfg_save(void)
{
    wchar_t p[MAX_PATH], d[MAX_PATH];
    FILE *f;
    int i;
    swprintf(d, MAX_PATH, L"%ls\\config", g_dir);
    CreateDirectoryW(d, NULL);
    cfg_path(p);
    f = _wfopen(p, L"wb");
    if (!f)
        return 0;
    for (i = 0; i < g_ncfg; i++)
        fprintf(f, "%s\n", g_cfg[i]);
    fclose(f);
    return 1;
}

/* ---------------------------------------------------------------- the launcher window */
enum { NAV_PLAY = 1, NAV_SETTINGS, NAV_SAVES, NAV_ABOUT };
enum { B_PLAY = 300, B_IMPORT, B_OPENSAVES, B_OPENLOG, B_UPDATE, B_CHECK, B_GITHUB, B_UNINSTALL, B_DEFAULTS,
       B_OPENFOLDER, SEL_BASE = 400, SEL_PREV = 500, VOL = 600 };

static const wchar_t *const k_names[] = {
    L"Resolution scale", L"Output resolution", L"Display", L"Speed Force", L"Upscaler",
    L"Anti-aliasing", L"Texture filtering", L"Button icons", L"FPS counter"};
static const wchar_t *const k_desc[] = {
    L"The game is drawn at 720p times this, then scaled to your screen.",
    L"The resolution of the picture sent to your screen.",
    L"Fullscreen or a window (F11 switches in game).",
    L"Frame generation: new frames between the game's own, up to your monitor's rate.",
    L"DLSS, FSR or XeSS when the resolution scale is below your screen size.",
    L"Smooths jagged edges.",
    L"Sharper textures at an angle.",
    L"The button prompts shown in game.",
    L"Shows the frame rate in a corner."};

static struct {
    int nav;
    int sel[16];
    int volume;
    int dragging;
    RECT vol_track;
    wchar_t status[160];
    int update_kind;                 /* -1 checking, 0 latest, 1 newer, 2 offline */
    wchar_t update_tag[64];
    GpImage *logo, *banner;
    int toast;                       /* ticks left of the "Saved" note */
    int importing;
    wchar_t slots[5][96];
} L;

/* "v1.2.3" / "1.2" -> comparable number */
static long version_num(const char *v)
{
    long part[3] = {0, 0, 0};
    int i = 0;
    while (*v && (*v < '0' || *v > '9'))
        v++;
    while (*v && i < 3) {
        part[i] = strtol(v, (char **)&v, 10);
        i++;
        if (*v != '.')
            break;
        v++;
    }
    return part[0] * 1000000 + part[1] * 1000 + part[2];
}

/* The value of "key": "..." in a JSON text (enough for GitHub's release object). */
static int json_str(const char *j, const char *key, char *out, size_t n)
{
    char pat[64];
    const char *p;
    size_t k = 0;
    snprintf(pat, sizeof pat, "\"%s\"", key);
    p = strstr(j, pat);
    if (!p)
        return 0;
    p = strchr(p + strlen(pat), '"');
    if (!p)
        return 0;
    for (p++; *p && *p != '"' && k + 1 < n; p++)
        out[k++] = *p;
    out[k] = 0;
    return k > 0;
}

static DWORD WINAPI update_thread(void *arg)
{
    static char body[65536];
    char tag[64], url[400];
    wchar_t path[256];
    HINTERNET s, c = NULL, r = NULL;
    DWORD got = 0, n, status = 0, sl = sizeof status;
    int newer = -1;                                   /* -1 unknown, 0 latest, 1 newer */
    (void)arg;
    swprintf(path, 256, L"/repos/%hs/releases/latest", SF_GITHUB_REPO);
    s = WinHttpOpen(L"SpeedForceLauncher/" SF_VERSION_W, WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                    WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (s) {
        WinHttpSetTimeouts(s, 5000, 5000, 5000, 8000);
        c = WinHttpConnect(s, L"api.github.com", INTERNET_DEFAULT_HTTPS_PORT, 0);
    }
    if (c)
        r = WinHttpOpenRequest(c, L"GET", path, NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES,
                               WINHTTP_FLAG_SECURE);
    if (r && WinHttpSendRequest(r, L"Accept: application/vnd.github+json\r\n", (DWORD)-1L,
                                WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
        WinHttpReceiveResponse(r, NULL)) {
        WinHttpQueryHeaders(r, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                            &status, &sl, WINHTTP_NO_HEADER_INDEX);
        while (got + 1 < sizeof body && WinHttpReadData(r, body + got, (DWORD)(sizeof body - 1 - got), &n) && n)
            got += n;
        body[got] = 0;
        if (status == 200 && json_str(body, "tag_name", tag, sizeof tag)) {
            newer = version_num(tag) > version_num(SF_VERSION);
            if (newer) {
                if (!json_str(body, "html_url", url, sizeof url))
                    snprintf(url, sizeof url, "https://github.com/%s/releases/latest", SF_GITHUB_REPO);
                MultiByteToWideChar(CP_UTF8, 0, url, -1, g_update_url, 512);
                {
                    wchar_t *t = (wchar_t *)malloc(64 * sizeof(wchar_t));
                    MultiByteToWideChar(CP_UTF8, 0, tag, -1, t, 64);
                    PostMessageW(g_wnd, WM_APP_UPDATE, 1, (LPARAM)t);
                }
            }
        }
    }
    if (r) WinHttpCloseHandle(r);
    if (c) WinHttpCloseHandle(c);
    if (s) WinHttpCloseHandle(s);
    if (newer != 1)
        PostMessageW(g_wnd, WM_APP_UPDATE, newer == 0 ? 0 : 2, 0);
    return 0;
}

static void check_updates(void)
{
    L.update_kind = -1;
    CloseHandle(CreateThread(NULL, 0, update_thread, NULL, 0, NULL));
}

static void on_update(int kind, wchar_t *tag)
{
    L.update_kind = kind;
    if (kind == 1 && tag)
        wcsncpy(L.update_tag, tag, 63);
    free(tag);
    InvalidateRect(ui.wnd, NULL, FALSE);
}

static void settings_load(void)
{
    size_t i;
    char v[64];
    cfg_load();
    for (i = 0; i < NCHOICES; i++) {
        Choice *c = &g_choices[i];
        int k, sel = 0;
        if (!cfg_get(c->key, v, sizeof v))
            strcpy(v, c->def);
        for (k = 0; c->vals[k]; k++)
            if (!_stricmp(c->vals[k], v))
                sel = k;
        L.sel[i] = sel;
    }
    L.volume = cfg_get("audio.volume", v, sizeof v) ? atoi(v) : 100;
}

static void settings_save(void)
{
    size_t i;
    char v[16];
    cfg_load();                       /* the game may have changed it since */
    for (i = 0; i < NCHOICES; i++)
        cfg_set(g_choices[i].key, g_choices[i].vals[L.sel[i]], g_choices[i].quoted);
    snprintf(v, sizeof v, "%d", L.volume);
    cfg_set("audio.volume", v, 0);
    if (cfg_save())
        L.toast = 40;
}

static int count_choices(size_t i)
{
    int n = 0;
    while (g_choices[i].vals[n]) n++;
    return n;
}

static void scan_saves(void)
{
    int n;
    for (n = 1; n <= 5; n++) {
        wchar_t p[MAX_PATH];
        char lvl[16] = "";
        FILE *f;
        WIN32_FILE_ATTRIBUTE_DATA a;
        swprintf(p, MAX_PATH, L"%ls\\saves\\UDATA\\57520001\\%012llX\\slot.bin", g_dir,
                 0xACCD073B22C1ull + 0x3Bull * (unsigned long long)(n - 1));
        f = _wfopen(p, L"rb");
        if (!f) {
            swprintf(L.slots[n - 1], 96, L"Empty");
            continue;
        }
        fread(lvl, 1, 15, f);
        fclose(f);
        lvl[15] = 0;
        GetFileAttributesExW(p, GetFileExInfoStandard, &a);
        {
            SYSTEMTIME st, lt;
            FileTimeToSystemTime(&a.ftLastWriteTime, &st);
            SystemTimeToTzSpecificLocalTime(NULL, &st, &lt);
            swprintf(L.slots[n - 1], 96, L"%hs%ls  -  saved %04d-%02d-%02d %02d:%02d", lvl,
                     !strcmp(lvl, "e11l5") ? L" (final mission / completed)" : L"",
                     lt.wYear, lt.wMonth, lt.wDay, lt.wHour, lt.wMinute);
        }
    }
}

/* -- painting */
static void nav_item(int y, int id, const wchar_t *t)
{
    RECT r = R(12, y, 196, 40);
    int on = L.nav == id;
    if (on) ui_round(r, 8, C_CARD2, 0);
    else if (ui.hot == id) ui_round(r, 8, C_HOVER, 0);
    if (on) ui_round(R(12, y + 10, 3, 20), 2, C_ACCENT, 0);
    r.left += S(18);
    ui_text(r, t, on ? ui.f_bold : ui.f_body, on ? C_TEXT : C_SUB, DT_VCENTER | DT_SINGLELINE);
    ui_hit(R(12, y, 196, 40), id, UI_NAV);
}

static void paint_sidebar(void)
{
    RECT side = R(0, 0, 220, 700);
    HBRUSH b = CreateSolidBrush(ui_cr(C_BG2));
    FillRect(ui.dc, &side, b);
    DeleteObject(b);
    if (L.logo) ui_image(L.logo, R(22, 22, 36, 36));
    ui_text(R(68, 22, 150, 36), L"Speed Force", ui.f_h2, C_TEXT, DT_VCENTER | DT_SINGLELINE);
    nav_item(84, NAV_PLAY, L"Play");
    nav_item(128, NAV_SETTINGS, L"Settings");
    nav_item(172, NAV_SAVES, L"Saves");
    nav_item(216, NAV_ABOUT, L"About");
    ui_text(R(24, 600, 180, 18), L"Version " SF_VERSION_W, ui.f_small, C_DIM, DT_SINGLELINE);
    if (L.update_kind == 1) {
        ui_round(R(16, 540, 188, 48), 8, RGBA(255, 196, 40, 30), C_ACCENT);
        ui_text(R(28, 544, 170, 20), L"Update available", ui.f_bold, C_ACCENT, DT_SINGLELINE);
        ui_link(R(28, 564, 170, 20), B_UPDATE, L.update_tag);
    }
}

static const wchar_t *choice_label(size_t i)
{
    return g_choices[i].labels[L.sel[i]];
}

static void paint_play(void)
{
    wchar_t t[200];
    RECT hero = R(248, 28, 708, 300);
    ui_round(hero, 14, C_CARD, C_BORDER);
    if (L.banner) ui_image(L.banner, R(249, 29, 706, 298));
    ui_text(R(280, 170, 600, 40), L"Justice League Heroes", ui.f_title, C_TEXT, DT_SINGLELINE);
    ui_text(R(282, 210, 600, 20), L"Native on Windows  -  Speed Force " SF_VERSION_W, ui.f_body, C_SUB, DT_SINGLELINE);
    ui_button(R(280, 246, 200, 52), B_PLAY, L"Play", 1, L.status[0] == 0);
    if (L.status[0])
        ui_text(R(500, 246, 420, 52), L.status, ui.f_small, C_BAD, DT_VCENTER | DT_WORDBREAK);

    ui_round(R(248, 346, 708, 150), 12, C_CARD, C_BORDER);
    ui_text(R(272, 362, 400, 22), L"Current settings", ui.f_h2, C_TEXT, DT_SINGLELINE);
    swprintf(t, 200, L"%ls  -  output %ls  -  %ls", choice_label(0), choice_label(1), choice_label(2));
    ui_text(R(272, 396, 660, 20), t, ui.f_body, C_SUB, DT_SINGLELINE | DT_END_ELLIPSIS);
    swprintf(t, 200, L"Speed Force %ls  -  upscaler %ls  -  anti-aliasing %ls", choice_label(3), choice_label(4),
             choice_label(5));
    ui_text(R(272, 420, 660, 20), t, ui.f_body, C_SUB, DT_SINGLELINE | DT_END_ELLIPSIS);
    ui_link(R(272, 452, 200, 24), NAV_SETTINGS + 1000, L"Change settings  >");

    ui_text(R(250, 512, 700, 40),
            L"Tip: \"Speed Force (game only)\" in the Start menu starts the game without the launcher. "
            L"Press F10 in game for every setting.", ui.f_small, C_DIM, DT_WORDBREAK);
}

static void selector(int x, int y, size_t i)
{
    RECT row = R(x, y, 348, 54);
    int hot = ui.hot == SEL_BASE + (int)i || ui.hot == SEL_PREV + (int)i;
    ui_round(row, 10, hot ? C_CARD2 : C_CARD, C_BORDER);
    ui_text(R(x + 16, y, 160, 54), k_names[i], ui.f_bold, C_TEXT, DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    ui_round(R(x + 176, y + 10, 160, 34), 8, C_INPUT, C_BORDER);
    ui_text(R(x + 178, y + 10, 26, 34), L"\x2039", ui.f_h1, ui.hot == SEL_PREV + (int)i ? C_ACCENT : C_SUB,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    ui_text(R(x + 308, y + 10, 26, 34), L"\x203A", ui.f_h1, ui.hot == SEL_BASE + (int)i ? C_ACCENT : C_SUB,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    ui_text(R(x + 202, y + 10, 108, 34), choice_label(i), ui.f_bold, C_TEXT,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    ui_hit(R(x + 176, y + 10, 32, 34), SEL_PREV + (int)i, UI_PREV);
    ui_hit(R(x + 208, y + 10, 128, 34), SEL_BASE + (int)i, UI_NEXT);
}

static void paint_settings(void)
{
    size_t i;
    wchar_t t[16];
    const wchar_t *desc = L"Click a value to change it (the arrow on the left goes back).";
    ui_text(R(248, 22, 400, 34), L"Settings", ui.f_h1, C_TEXT, DT_SINGLELINE);
    ui_text(R(250, 56, 700, 18), L"The same settings as the in-game F10 menu, which has the rest. Changes are saved at once.",
            ui.f_small, C_SUB, DT_SINGLELINE);
    for (i = 0; i < NCHOICES; i++) {
        selector(248 + (int)(i % 2) * 360, 88 + (int)(i / 2) * 62, i);
        if (ui.hot == SEL_BASE + (int)i || ui.hot == SEL_PREV + (int)i) desc = k_desc[i];
    }
    /* volume: the tenth cell */
    {
        int x = 248 + 360, y = 88 + 4 * 62;
        RECT knob;
        double f = L.volume / 100.0;
        ui_round(R(x, y, 348, 54), 10, ui.hot == VOL ? C_CARD2 : C_CARD, C_BORDER);
        ui_text(R(x + 16, y, 150, 54), L"Master volume", ui.f_bold, C_TEXT, DT_VCENTER | DT_SINGLELINE);
        L.vol_track = R(x + 168, y + 24, 120, 6);
        ui_progress(L.vol_track, f, C_ACCENT2, C_ACCENT);
        knob.left = L.vol_track.left + (LONG)((L.vol_track.right - L.vol_track.left) * f);
        ui_circle((float)knob.left, (float)(L.vol_track.top + S(3)), SF(8), C_TEXT, 0, 0);
        swprintf(t, 16, L"%d%%", L.volume);
        ui_text(R(x + 292, y, 44, 54), t, ui.f_bold, C_TEXT, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
        ui_hit(R(x + 160, y + 8, 136, 38), VOL, UI_SLIDER);
        if (ui.hot == VOL) desc = L"The game's overall loudness.";
    }
    ui_round(R(248, 412, 708, 64), 10, C_BG2, C_BORDER);
    ui_text(R(268, 412, 670, 64), desc, ui.f_body, C_SUB, DT_VCENTER | DT_WORDBREAK);
    ui_link(R(250, 492, 200, 24), B_DEFAULTS, L"Restore defaults");
    if (L.toast > 0)
        ui_text(R(760, 22, 196, 34), L"Saved", ui.f_bold, C_OK, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
}

static void paint_saves(void)
{
    int n;
    ui_text(R(248, 22, 400, 34), L"Saves", ui.f_h1, C_TEXT, DT_SINGLELINE);
    ui_text(R(250, 56, 700, 18), L"Your five save slots, kept in the saves folder inside the install folder.", ui.f_small,
            C_SUB, DT_SINGLELINE);
    for (n = 0; n < 5; n++) {
        int y = 88 + n * 56;
        wchar_t h[16];
        ui_round(R(248, y, 708, 48), 10, C_CARD, C_BORDER);
        swprintf(h, 16, L"Slot %d", n + 1);
        ui_text(R(268, y, 80, 48), h, ui.f_bold, C_TEXT, DT_VCENTER | DT_SINGLELINE);
        ui_text(R(350, y, 590, 48), L.slots[n], ui.f_body, wcscmp(L.slots[n], L"Empty") ? C_TEXT : C_DIM,
                DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    }
    ui_round(R(248, 378, 708, 120), 12, C_CARD, C_BORDER);
    ui_text(R(272, 394, 600, 22), L"Bring saves from a real Xbox", ui.f_h2, C_TEXT, DT_SINGLELINE);
    ui_text(R(272, 420, 660, 36),
            L"Choose the folder you copied from your Xbox (UDATA\\57520001). Saves go into free slots; completed saves "
            L"start Episode 1 the Chapter Select way.", ui.f_small, C_SUB, DT_WORDBREAK);
    ui_button(R(272, 456, 180, 34), B_IMPORT, L.importing ? L"Importing..." : L"Import Xbox saves", 1, !L.importing);
    ui_button(R(462, 456, 180, 34), B_OPENSAVES, L"Open saves folder", 0, 1);
}

static void paint_about(void)
{
    wchar_t t[200];
    ui_text(R(248, 22, 400, 34), L"About", ui.f_h1, C_TEXT, DT_SINGLELINE);
    ui_round(R(248, 72, 708, 150), 12, C_CARD, C_BORDER);
    if (L.logo) ui_image(L.logo, R(272, 96, 56, 56));
    ui_text(R(344, 92, 560, 28), L"Speed Force " SF_VERSION_W, ui.f_h2, C_TEXT, DT_SINGLELINE);
    ui_text(R(344, 120, 580, 40), L"An unofficial Justice League Heroes native Windows recompilation. Fan project, not "
            L"affiliated with Warner Bros. Games, DC, Snowblind Studios or Eidos.", ui.f_small, C_SUB, DT_WORDBREAK);
    if (L.update_kind == -1) wcscpy(t, L"Checking for updates...");
    else if (L.update_kind == 0) wcscpy(t, L"You have the latest version.");
    else if (L.update_kind == 1) swprintf(t, 200, L"A new version is available: %ls", L.update_tag);
    else wcscpy(t, L"Couldn't check for updates (offline?).");
    ui_text(R(344, 170, 380, 34), t, ui.f_body, L.update_kind == 1 ? C_ACCENT : C_SUB, DT_VCENTER | DT_SINGLELINE);
    if (L.update_kind == 1) ui_button(R(740, 170, 196, 34), B_UPDATE, L"Get the update", 1, 1);
    else ui_button(R(740, 170, 196, 34), B_CHECK, L"Check again", 0, L.update_kind != -1);

    ui_round(R(248, 238, 708, 150), 12, C_CARD, C_BORDER);
    ui_text(R(272, 254, 600, 22), L"Files", ui.f_h2, C_TEXT, DT_SINGLELINE);
    ui_text(R(272, 280, 660, 20), g_dir, ui.f_small, C_SUB, DT_SINGLELINE | DT_PATH_ELLIPSIS);
    ui_button(R(272, 312, 160, 34), B_OPENFOLDER, L"Open folder", 0, 1);
    ui_button(R(442, 312, 160, 34), B_OPENLOG, L"Open game log", 0, 1);
    ui_button(R(612, 312, 160, 34), B_GITHUB, L"GitHub page", 0, 1);

    ui_round(R(248, 404, 708, 100), 12, C_CARD, C_BORDER);
    ui_text(R(272, 420, 600, 22), L"Uninstall", ui.f_h2, C_TEXT, DT_SINGLELINE);
    ui_text(R(272, 446, 480, 40), L"Removes Speed Force from this PC. You can keep your saves and settings.", ui.f_small,
            C_SUB, DT_WORDBREAK);
    ui_button(R(776, 440, 160, 36), B_UNINSTALL, L"Uninstall", 3, 1);
}

static void paint(void)
{
    UiPaint p;
    ui_begin(&p);
    paint_sidebar();
    if (L.nav == NAV_PLAY) paint_play();
    else if (L.nav == NAV_SETTINGS) paint_settings();
    else if (L.nav == NAV_SAVES) paint_saves();
    else paint_about();
    ui_end(&p);
}

/* -- actions */
static void play(void)
{
    wchar_t exe[MAX_PATH];
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    swprintf(exe, MAX_PATH, L"%ls\\SpeedForce.exe", g_dir);
    memset(&si, 0, sizeof si);
    si.cb = sizeof si;
    if (CreateProcessW(exe, NULL, NULL, NULL, FALSE, 0, NULL, g_dir, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        PostMessageW(ui.wnd, WM_CLOSE, 0, 0);
    } else {
        wcscpy(L.status, L"SpeedForce.exe could not be started. Run the Speed Force setup again.");
    }
}

static void open_path(const wchar_t *rel)
{
    wchar_t p[MAX_PATH];
    swprintf(p, MAX_PATH, rel[0] ? L"%ls\\%ls" : L"%ls", g_dir, rel);
    ShellExecuteW(ui.wnd, L"open", p, NULL, g_dir, SW_SHOWNORMAL);
}

static DWORD WINAPI import_thread(void *arg)
{
    wchar_t *cmd = (wchar_t *)arg;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    DWORD code = 1;
    memset(&si, 0, sizeof si);
    si.cb = sizeof si;
    if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, g_dir, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, INFINITE);
        GetExitCodeProcess(pi.hProcess, &code);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
    free(cmd);
    PostMessageW(ui.wnd, WM_APP_DONE, code, 0);
    return 0;
}

static void import_saves(void)
{
    wchar_t s[MAX_PATH] = L"", *cmd;
    if (!ui_pick(s, 1, L"The folder with your Xbox saves (UDATA\\57520001)", NULL, NULL))
        return;
    cmd = (wchar_t *)malloc(4096 * sizeof(wchar_t));
    swprintf(cmd, 4096, L"\"%ls\\_build\\python\\python.exe\" \"%ls\\_build\\setup\\sf_saves.py\" --in \"%ls\" --out \"%ls\\saves\"",
             g_dir, g_dir, s, g_dir);
    L.importing = 1;
    CloseHandle(CreateThread(NULL, 0, import_thread, cmd, 0, NULL));
}

/* Remove everything but saves\ and config\ (unless asked), the shortcuts and the Windows entry. */
static void delete_tree(const wchar_t *dir, int top, int keep_user)
{
    wchar_t pat[MAX_PATH * 2], self[MAX_PATH];
    WIN32_FIND_DATAW fd;
    HANDLE h;
    GetModuleFileNameW(NULL, self, MAX_PATH);
    swprintf(pat, MAX_PATH * 2, L"%ls\\*", dir);
    h = FindFirstFileW(pat, &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        wchar_t p[MAX_PATH * 2];
        if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..")) continue;
        if (top && keep_user && (!_wcsicmp(fd.cFileName, L"saves") || !_wcsicmp(fd.cFileName, L"config"))) continue;
        swprintf(p, MAX_PATH * 2, L"%ls\\%ls", dir, fd.cFileName);
        if (!_wcsicmp(p, self)) continue;
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            delete_tree(p, 0, keep_user);
            RemoveDirectoryW(p);
        } else {
            SetFileAttributesW(p, FILE_ATTRIBUTE_NORMAL);
            DeleteFileW(p);
        }
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

static int uninstall(int quiet)
{
    int keep = 1, r;
    wchar_t *progs = NULL, *desk = NULL, p[MAX_PATH], self[MAX_PATH], cmd[MAX_PATH * 3];
    if (!quiet) {
        r = MessageBoxW(ui.wnd, L"Uninstall Speed Force?\n\nYes: uninstall and keep your saves and settings.\n"
                                L"No: uninstall and delete your saves and settings too.\nCancel: keep Speed Force.",
                        L"Uninstall Speed Force", MB_YESNOCANCEL | MB_ICONQUESTION | MB_DEFBUTTON1);
        if (r == IDCANCEL) return 0;
        keep = r == IDYES;
    }
    delete_tree(g_dir, 1, keep);
    if (SUCCEEDED(SHGetKnownFolderPath(&FOLDERID_Programs, 0, NULL, &progs))) {
        swprintf(p, MAX_PATH, L"%ls\\Speed Force\\Speed Force.lnk", progs);
        DeleteFileW(p);
        swprintf(p, MAX_PATH, L"%ls\\Speed Force\\Speed Force (game only).lnk", progs);
        DeleteFileW(p);
        swprintf(p, MAX_PATH, L"%ls\\Speed Force", progs);
        RemoveDirectoryW(p);
        CoTaskMemFree(progs);
    }
    if (SUCCEEDED(SHGetKnownFolderPath(&FOLDERID_Desktop, 0, NULL, &desk))) {
        swprintf(p, MAX_PATH, L"%ls\\Speed Force.lnk", desk);
        DeleteFileW(p);
        CoTaskMemFree(desk);
    }
    RegDeleteTreeW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SpeedForce");
    /* this program removes itself (and the folder, when empty) once it has closed */
    GetModuleFileNameW(NULL, self, MAX_PATH);
    swprintf(cmd, MAX_PATH * 3, L"cmd.exe /c ping 127.0.0.1 -n 3 >nul & del /f /q \"%ls\" & rmdir \"%ls\"", self, g_dir);
    {
        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        memset(&si, 0, sizeof si);
        si.cb = sizeof si;
        if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
        }
    }
    if (!quiet)
        MessageBoxW(ui.wnd, keep ? L"Speed Force was uninstalled. Your saves and settings are still in its folder."
                                 : L"Speed Force was uninstalled.", L"Speed Force", MB_ICONINFORMATION);
    return 1;
}

static void set_volume_from(int x)
{
    int w = L.vol_track.right - L.vol_track.left, v;
    if (w <= 0) return;
    v = (x - L.vol_track.left) * 100 / w;
    if (v < 0) v = 0;
    if (v > 100) v = 100;
    L.volume = v;
}

static void command(int id)
{
    if (id >= NAV_PLAY && id <= NAV_ABOUT) {
        L.nav = id;
        if (id == NAV_SAVES) scan_saves();
    } else if (id == NAV_SETTINGS + 1000) {
        L.nav = NAV_SETTINGS;
    } else if (id >= SEL_PREV && id < SEL_PREV + (int)NCHOICES) {
        size_t i = (size_t)(id - SEL_PREV);
        int n = count_choices(i);
        L.sel[i] = (L.sel[i] + n - 1) % n;
        settings_save();
    } else if (id >= SEL_BASE && id < SEL_BASE + (int)NCHOICES) {
        size_t i = (size_t)(id - SEL_BASE);
        L.sel[i] = (L.sel[i] + 1) % count_choices(i);
        settings_save();
    } else {
        switch (id) {
        case B_PLAY: play(); break;
        case B_IMPORT: import_saves(); break;
        case B_OPENSAVES: {
            wchar_t p[MAX_PATH];
            swprintf(p, MAX_PATH, L"%ls\\saves", g_dir);
            CreateDirectoryW(p, NULL);
            open_path(L"saves");
            break;
        }
        case B_OPENLOG: open_path(L"SpeedForce.log"); break;
        case B_OPENFOLDER: open_path(L""); break;
        case B_UPDATE: if (g_update_url[0]) ShellExecuteW(ui.wnd, L"open", g_update_url, NULL, NULL, SW_SHOWNORMAL); break;
        case B_GITHUB: ShellExecuteW(ui.wnd, L"open", L"https://github.com/" SF_GITHUB_REPO_W, NULL, NULL, SW_SHOWNORMAL); break;
        case B_CHECK: check_updates(); break;
        case B_DEFAULTS: {
            size_t i;
            for (i = 0; i < NCHOICES; i++) {
                int k;
                for (k = 0; g_choices[i].vals[k]; k++)
                    if (!strcmp(g_choices[i].vals[k], g_choices[i].def)) L.sel[i] = k;
            }
            L.volume = 100;
            settings_save();
            break;
        }
        case B_UNINSTALL:
            if (uninstall(0)) PostMessageW(ui.wnd, WM_CLOSE, 0, 0);
            break;
        }
    }
    InvalidateRect(ui.wnd, NULL, FALSE);
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    switch (m) {
    case WM_PAINT: paint(); return 0;
    case WM_ERASEBKGND: return 1;
    case WM_SETCURSOR:
        if (LOWORD(lp) == HTCLIENT) return TRUE;
        break;
    case WM_LBUTTONDOWN: {
        int k = 0, id = ui_hit_test(GET_X_LPARAM(lp), GET_Y_LPARAM(lp), &k);
        if (id == VOL) {
            L.dragging = 1;
            SetCapture(h);
            set_volume_from(GET_X_LPARAM(lp));
            InvalidateRect(h, NULL, FALSE);
            return 0;
        }
        ui_mouse(m, lp, NULL);
        return 0;
    }
    case WM_MOUSEMOVE:
        if (L.dragging) {
            set_volume_from(GET_X_LPARAM(lp));
            InvalidateRect(h, NULL, FALSE);
            return 0;
        }
        ui_mouse(m, lp, NULL);
        return 0;
    case WM_MOUSELEAVE: ui_mouse(m, lp, NULL); return 0;
    case WM_LBUTTONUP:
        if (L.dragging) {
            L.dragging = 0;
            ReleaseCapture();
            settings_save();
            InvalidateRect(h, NULL, FALSE);
            return 0;
        } else {
            int id = ui_mouse(m, lp, NULL);
            if (id) command(id);
        }
        return 0;
    case WM_TIMER:
        if (L.toast > 0 && --L.toast == 0) InvalidateRect(h, NULL, FALSE);
        return 0;
    case WM_APP_UPDATE: on_update((int)wp, (wchar_t *)lp); return 0;
    case WM_APP_DONE:
        L.importing = 0;
        scan_saves();
        MessageBoxW(h, wp ? L"Some saves could not be imported; see import.log in the saves folder."
                          : L"Your saves were imported.", L"Speed Force", wp ? MB_ICONWARNING : MB_ICONINFORMATION);
        InvalidateRect(h, NULL, FALSE);
        return 0;
    case WM_DPICHANGED: {
        RECT *r = (RECT *)lp;
        ui.dpi = HIWORD(wp);
        ui_fonts();
        SetWindowPos(h, NULL, r->left, r->top, r->right - r->left, r->bottom - r->top, SWP_NOZORDER);
        return 0;
    }
    case WM_DESTROY: PostQuitMessage(0); return 0;
    }
    return DefWindowProcW(h, m, wp, lp);
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR cmdline, int show)
{
    WNDCLASSW wc;
    MSG msg;
    RECT r;
    DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
    int dpi, argc, i, un = 0, quiet = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    (void)prev;
    (void)cmdline;
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    GetModuleFileNameW(NULL, g_dir, MAX_PATH);
    *wcsrchr(g_dir, L'\\') = 0;
    for (i = 1; argv && i < argc; i++) {
        if (!_wcsicmp(argv[i], L"/uninstall")) un = 1;
        if (!_wcsicmp(argv[i], L"/quiet")) quiet = 1;
    }
    memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = wndproc;
    wc.hInstance = inst;
    wc.hIcon = LoadIconW(inst, MAKEINTRESOURCEW(1));
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = L"SpeedForceLauncher";
    RegisterClassW(&wc);
    dpi = (int)GetDpiForSystem();
    r.left = r.top = 0;
    r.right = MulDiv(980, dpi, 96);
    r.bottom = MulDiv(640, dpi, 96);
    AdjustWindowRectExForDpi(&r, style, FALSE, 0, (UINT)dpi);
    ui.wnd = g_wnd = CreateWindowW(L"SpeedForceLauncher", L"Speed Force", style, CW_USEDEFAULT, CW_USEDEFAULT,
                                   r.right - r.left, r.bottom - r.top, NULL, NULL, inst, NULL);
    ui_init(ui.wnd);
    if (un)
        return uninstall(quiet) ? 0 : 1;
    if (ui.dpi != dpi) {
        r.left = r.top = 0;
        r.right = S(980);
        r.bottom = S(640);
        AdjustWindowRectExForDpi(&r, style, FALSE, 0, (UINT)ui.dpi);
        SetWindowPos(ui.wnd, NULL, 0, 0, r.right - r.left, r.bottom - r.top, SWP_NOMOVE | SWP_NOZORDER);
    }
    L.logo = ui_png(101);
    L.banner = ui_png(102);
    L.nav = NAV_PLAY;
    {
        wchar_t exe[MAX_PATH];
        swprintf(exe, MAX_PATH, L"%ls\\SpeedForce.exe", g_dir);
        if (GetFileAttributesW(exe) == INVALID_FILE_ATTRIBUTES)
            wcscpy(L.status, L"Speed Force isn't built in this folder. Run the Speed Force setup to build it.");
    }
    settings_load();
    scan_saves();
    SetTimer(ui.wnd, 1, 50, NULL);
    check_updates();
    ShowWindow(ui.wnd, show);
    UpdateWindow(ui.wnd);
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return (int)msg.wParam;
}
