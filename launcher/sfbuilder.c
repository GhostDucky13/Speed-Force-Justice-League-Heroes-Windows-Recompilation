/*
 * sfbuilder.c - SpeedForce-Setup.exe: the Speed Force builder.
 *
 * One program: choose where to install and your own Xbox and PSP dumps (and, optionally, Xbox
 * saves), then it unpacks its build kit (carried at the end of this exe, see sfpack.c), runs the
 * build (_build\setup\sf_install.py, which prints "@@<per mille>|<text>" progress lines) and
 * installs SpeedForceLauncher.exe and SpeedForce.exe, with shortcuts and an entry in Windows'
 * installed apps (removed by "SpeedForceLauncher.exe /uninstall").
 *
 * Build: windres sfbuilder.rc -O coff -o sfbuilder.res
 *        clang -O2 -municode -mwindows sfbuilder.c sfbuilder.res -lgdiplus -ldwmapi -lcabinet
 *              -lole32 -luuid -lshell32 -lcomdlg32 -lshlwapi -o SpeedForceBuilder.exe
 */
#include "sfui.h"
#include <compressapi.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <shellapi.h>
#include <uxtheme.h>
#include <stdint.h>

#define SF_VERSION_W L"2.1.1"
#define NEED_GB 14
#define WM_APP_LINE (WM_APP + 1)
#define WM_APP_DONE (WM_APP + 2)
#define WM_APP_UNPACK (WM_APP + 3)

enum { ID_DIR = 100, ID_XBOX, ID_PSP, ID_SAVES,
       B_DIR = 200, B_XBOX, B_PSP, B_SAVES, B_NEXT, B_BACK, B_BUILD, B_CANCEL, B_DETAILS, B_PLAY, B_LAUNCHER,
       B_FOLDER, B_CLOSE, B_LOG, B_RETRY, C_SAVES, C_DESKTOP };

enum { P_FILES, P_OPTIONS, P_BUILD, P_DONE };

#define NSTEPS 9
static const wchar_t *const k_steps[NSTEPS] = {
    L"Unpack the build tools", L"Check your dumps", L"Read both discs", L"Rebuild the mod",
    L"Place the game files", L"Translate the game to C", L"Compile", L"Install", L"Clean up"};
static const double k_expect[NSTEPS] = {60, 70, 30, 1100, 5, 420, 400, 15, 20};   /* seconds */

static struct {
    int page;
    HWND e_dir, e_xbox, e_psp, e_saves, e_log;
    RECT box_dir, box_xbox, box_psp, box_saves;
    int saves_on, desktop;
    /* checks */
    int ok_dir, ok_xbox, ok_psp, ok_space;
    wchar_t msg_dir[256], msg_xbox[256], msg_psp[256], msg_space[256];
    int old_install;
    /* build */
    int building, failed, cancelled, details;
    int step;                                  /* 0..NSTEPS-1 active, NSTEPS done */
    double step_t0[NSTEPS + 1], step_dur[NSTEPS];
    double t0;
    double frac;                               /* 0..1 overall */
    wchar_t detail[256], error[512];
    HANDLE job, proc;
    volatile LONG stop;
    int spin;
    wchar_t app[MAX_PATH];
    wchar_t *log;
    size_t log_len, log_cap;
    GpImage *logo;
} g;

static double now_s(void) { return (double)GetTickCount64() / 1000.0; }

/* ---------------------------------------------------------------- checks */
static void get_text(HWND e, wchar_t *out)
{
    GetWindowTextW(e, out, MAX_PATH);
    {   /* trim spaces and quotes */
        wchar_t *p = out, *q;
        while (*p == L' ' || *p == L'"') p++;
        memmove(out, p, (wcslen(p) + 1) * sizeof(wchar_t));
        q = out + wcslen(out);
        while (q > out && (q[-1] == L' ' || q[-1] == L'"' || q[-1] == L'\\')) *--q = 0;
    }
}

static int read_at(const wchar_t *path, uint64_t off, void *buf, DWORD n)
{
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    LARGE_INTEGER li;
    DWORD got = 0;
    if (h == INVALID_HANDLE_VALUE) return 0;
    li.QuadPart = (LONGLONG)off;
    SetFilePointerEx(h, li, NULL, FILE_BEGIN);
    ReadFile(h, buf, n, &got, NULL);
    CloseHandle(h);
    return got == n;
}

static uint64_t file_size(const wchar_t *p)
{
    WIN32_FILE_ATTRIBUTE_DATA a;
    if (!GetFileAttributesExW(p, GetFileExInfoStandard, &a) || (a.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY))
        return 0;
    return ((uint64_t)a.nFileSizeHigh << 32) | a.nFileSizeLow;
}

static void validate(void)
{
    wchar_t p[MAX_PATH];
    char buf[32];
    /* install folder */
    get_text(g.e_dir, p);
    g.ok_dir = 0;
    g.old_install = 0;
    if (wcslen(p) < 3 || p[1] != L':' || p[2] != L'\\') {
        wcscpy(g.msg_dir, L"Choose a folder on a drive, for example C:\\Games\\Speed Force.");
    } else {
        wchar_t pf[MAX_PATH] = L"", t[MAX_PATH];
        ExpandEnvironmentStringsW(L"%ProgramFiles%", pf, MAX_PATH);
        if (pf[0] && !_wcsnicmp(p, pf, wcslen(pf))) {
            wcscpy(g.msg_dir, L"Program Files needs administrator rights. Choose a folder you own.");
        } else {
            g.ok_dir = 1;
            swprintf(t, MAX_PATH, L"%ls\\unins000.exe", p);
            if (GetFileAttributesW(t) != INVALID_FILE_ATTRIBUTES) {
                g.old_install = 1;
                wcscpy(g.msg_dir, L"Speed Force 1.0 is installed here. Uninstall it first (Windows Settings > Apps).");
                g.ok_dir = 0;
            } else {
                swprintf(t, MAX_PATH, L"%ls\\SpeedForce.exe", p);
                wcscpy(g.msg_dir, GetFileAttributesW(t) != INVALID_FILE_ATTRIBUTES
                                      ? L"Speed Force is already here: it is built again, your saves and settings stay."
                                      : L"Speed Force will be installed here.");
            }
        }
    }
    /* free space on the folder's drive */
    g.ok_space = 0;
    if (wcslen(p) >= 3) {
        wchar_t root[4] = {p[0], L':', L'\\', 0};
        ULARGE_INTEGER fr;
        if (GetDiskFreeSpaceExW(root, &fr, NULL, NULL)) {
            double gb = (double)fr.QuadPart / 1073741824.0;
            g.ok_space = gb >= NEED_GB;
            swprintf(g.msg_space, 256, L"%.0f GB free on %lc:  -  needs about %d GB while building, about 5 GB afterwards.",
                     gb, p[0], NEED_GB);
        } else {
            wcscpy(g.msg_space, L"That drive can't be found.");
        }
    } else {
        g.msg_space[0] = 0;
    }
    /* Xbox dump */
    get_text(g.e_xbox, p);
    g.ok_xbox = 0;
    if (!p[0]) {
        wcscpy(g.msg_xbox, L"Choose your dump of the Xbox disc (.iso or .xiso).");
    } else if (file_size(p) < (100u << 20)) {
        wcscpy(g.msg_xbox, L"That file can't be read, or it is too small to be a disc image.");
    } else {
        static const uint64_t parts[] = {0, 0x18300000ull, 0x2080000ull, 0xFD90000ull};
        size_t i;
        for (i = 0; i < 4 && !g.ok_xbox; i++)
            if (read_at(p, parts[i] + 32 * 2048, buf, 20) && !memcmp(buf, "MICROSOFT*XBOX*MEDIA", 20))
                g.ok_xbox = 1;
        wcscpy(g.msg_xbox, g.ok_xbox ? L"Xbox game disc found. It is checked in full when the build starts."
                                     : L"This isn't an Xbox game disc image.");
    }
    /* PSP dump */
    get_text(g.e_psp, p);
    g.ok_psp = 0;
    if (!p[0]) {
        wcscpy(g.msg_psp, L"Choose your dump of the PSP disc (.iso).");
    } else if (file_size(p) < (50u << 20)) {
        wcscpy(g.msg_psp, L"That file can't be read, or it is too small to be a disc image.");
    } else {
        g.ok_psp = read_at(p, 0x8000, buf, 16) && !memcmp(buf + 1, "CD001", 5) && !memcmp(buf + 8, "PSP GAME", 8);
        wcscpy(g.msg_psp, g.ok_psp ? L"PSP game disc (UMD) found. It is checked in full when the build starts."
                                   : L"This isn't a PSP game disc image.");
    }
    InvalidateRect(ui.wnd, NULL, FALSE);
}

/* ---------------------------------------------------------------- log */
static void log_add(const wchar_t *s)
{
    size_t n = wcslen(s);
    if (g.log_len + n + 3 > g.log_cap) {
        g.log_cap = (g.log_cap + n + 3) * 2;
        g.log = (wchar_t *)realloc(g.log, g.log_cap * sizeof(wchar_t));
    }
    memcpy(g.log + g.log_len, s, n * sizeof(wchar_t));
    g.log_len += n;
    g.log[g.log_len++] = L'\r';
    g.log[g.log_len++] = L'\n';
    g.log[g.log_len] = 0;
    if (g.e_log && g.details) {
        int len = GetWindowTextLengthW(g.e_log);
        SendMessageW(g.e_log, EM_SETSEL, (WPARAM)len, (LPARAM)len);
        SendMessageW(g.e_log, EM_REPLACESEL, 0, (LPARAM)s);
        SendMessageW(g.e_log, EM_REPLACESEL, 0, (LPARAM)L"\r\n");
    }
}

static void post_line(const char *line)
{
    int wl = MultiByteToWideChar(CP_UTF8, 0, line, -1, NULL, 0);
    wchar_t *w = (wchar_t *)malloc(sizeof(wchar_t) * (size_t)(wl > 0 ? wl : 1));
    MultiByteToWideChar(CP_UTF8, 0, line, -1, w, wl);
    PostMessageW(ui.wnd, WM_APP_LINE, 0, (LPARAM)w);
}

/* ---------------------------------------------------------------- unpack (step 1) */
static int mkdirs(const wchar_t *path)
{
    wchar_t t[MAX_PATH * 2];
    size_t i;
    wcscpy(t, path);
    for (i = 3; t[i]; i++)
        if (t[i] == L'\\') {
            t[i] = 0;
            CreateDirectoryW(t, NULL);
            t[i] = L'\\';
        }
    return CreateDirectoryW(t, NULL) || GetLastError() == ERROR_ALREADY_EXISTS;
}

static int unpack(void)
{
    wchar_t self[MAX_PATH];
    HANDLE h;
    LARGE_INTEGER sz, pos;
    uint64_t arc_size, base, total, done = 0;
    char magic[8];
    DWORD got;
    uint32_t ver, files, i;
    char **paths;
    uint64_t *sizes;
    DECOMPRESSOR_HANDLE dc;
    unsigned char *comp = NULL, *raw = NULL;
    uint32_t cur = 0;
    uint64_t left_in_file = 0;
    HANDLE out = INVALID_HANDLE_VALUE;
    int ok = 0;

    GetModuleFileNameW(NULL, self, MAX_PATH);
    h = CreateFileW(self, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    if (h == INVALID_HANDLE_VALUE) {
        wcscpy(g.error, L"The setup can't read itself.");
        return 0;
    }
    GetFileSizeEx(h, &sz);
    pos.QuadPart = sz.QuadPart - 16;
    SetFilePointerEx(h, pos, NULL, FILE_BEGIN);
    ReadFile(h, &arc_size, 8, &got, NULL);
    ReadFile(h, magic, 8, &got, NULL);
    if (memcmp(magic, "SFPAYLD2", 8) || arc_size > (uint64_t)sz.QuadPart) {
        CloseHandle(h);
        wcscpy(g.error, L"The setup is incomplete (its build kit is missing). Download it again.");
        return 0;
    }
    base = (uint64_t)sz.QuadPart - arc_size;
    pos.QuadPart = (LONGLONG)base;
    SetFilePointerEx(h, pos, NULL, FILE_BEGIN);
    ReadFile(h, magic, 4, &got, NULL);
    ReadFile(h, &ver, 4, &got, NULL);
    ReadFile(h, &files, 4, &got, NULL);
    ReadFile(h, &total, 8, &got, NULL);
    paths = (char **)calloc(files, sizeof(char *));
    sizes = (uint64_t *)calloc(files, sizeof(uint64_t));
    for (i = 0; i < files; i++) {
        uint16_t l;
        ReadFile(h, &l, 2, &got, NULL);
        paths[i] = (char *)calloc(1, (size_t)l + 1);
        ReadFile(h, paths[i], l, &got, NULL);
        ReadFile(h, &sizes[i], 8, &got, NULL);
    }
    if (!CreateDecompressor(COMPRESS_ALGORITHM_LZMS, NULL, &dc)) {
        CloseHandle(h);
        wcscpy(g.error, L"Windows' decompressor isn't available (Windows 8 or later is needed).");
        return 0;
    }
    comp = (unsigned char *)malloc(64u << 20);
    raw = (unsigned char *)malloc(33u << 20);
    i = 0;
    while (!g.stop) {
        uint32_t rl, cl, off = 0;
        SIZE_T outl = 0;
        if (!ReadFile(h, &rl, 4, &got, NULL) || got != 4 || rl == 0)
            break;
        ReadFile(h, &cl, 4, &got, NULL);
        if (cl > (64u << 20) || rl > (33u << 20)) break;
        ReadFile(h, comp, cl, &got, NULL);
        if (got != cl || !Decompress(dc, comp, cl, raw, rl, &outl) || outl != rl) {
            wcscpy(g.error, L"The setup file is damaged. Download it again.");
            goto end;
        }
        while (off < rl) {
            DWORD w, n;
            while (left_in_file == 0 && out == INVALID_HANDLE_VALUE) {
                wchar_t rel[MAX_PATH], full[MAX_PATH * 2], *slash;
                size_t k;
                if (cur >= files) break;
                MultiByteToWideChar(CP_UTF8, 0, paths[cur], -1, rel, MAX_PATH);
                for (k = 0; rel[k]; k++)
                    if (rel[k] == L'/') rel[k] = L'\\';
                swprintf(full, MAX_PATH * 2, L"%ls\\%ls", g.app, rel);
                slash = wcsrchr(full, L'\\');
                *slash = 0;
                mkdirs(full);
                *slash = L'\\';
                out = CreateFileW(full, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
                if (out == INVALID_HANDLE_VALUE) {
                    swprintf(g.error, 512, L"Can't write %ls (is Speed Force still running?)", full);
                    goto end;
                }
                left_in_file = sizes[cur];
                cur++;
                if (left_in_file == 0) {
                    CloseHandle(out);
                    out = INVALID_HANDLE_VALUE;
                }
            }
            if (out == INVALID_HANDLE_VALUE) break;
            n = (DWORD)((rl - off) < left_in_file ? (rl - off) : left_in_file);
            WriteFile(out, raw + off, n, &w, NULL);
            off += n;
            left_in_file -= n;
            if (left_in_file == 0) {
                CloseHandle(out);
                out = INVALID_HANDLE_VALUE;
            }
        }
        done += rl;
        PostMessageW(ui.wnd, WM_APP_UNPACK, (WPARAM)(done * 1000 / (total ? total : 1)), 0);
    }
    ok = !g.stop && done == total;
    if (!ok && !g.error[0] && !g.stop)
        wcscpy(g.error, L"The setup file is incomplete. Download it again.");
end:
    if (out != INVALID_HANDLE_VALUE) CloseHandle(out);
    CloseDecompressor(dc);
    CloseHandle(h);
    free(comp);
    free(raw);
    for (i = 0; i < files; i++) free(paths[i]);
    free(paths);
    free(sizes);
    return ok;
}

/* ---------------------------------------------------------------- shortcuts, uninstall entry */
static void shortcut(const wchar_t *lnk, const wchar_t *target, const wchar_t *desc)
{
    IShellLinkW *sl;
    IPersistFile *pf;
    if (FAILED(CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, &IID_IShellLinkW, (void **)&sl)))
        return;
    sl->lpVtbl->SetPath(sl, target);
    sl->lpVtbl->SetWorkingDirectory(sl, g.app);
    sl->lpVtbl->SetDescription(sl, desc);
    sl->lpVtbl->SetIconLocation(sl, target, 0);
    if (SUCCEEDED(sl->lpVtbl->QueryInterface(sl, &IID_IPersistFile, (void **)&pf))) {
        pf->lpVtbl->Save(pf, lnk, TRUE);
        pf->lpVtbl->Release(pf);
    }
    sl->lpVtbl->Release(sl);
}

static void finish_install(void)
{
    wchar_t *progs = NULL, *desk = NULL, dir[MAX_PATH], lnk[MAX_PATH], tgt[MAX_PATH], game[MAX_PATH];
    HKEY k;
    swprintf(tgt, MAX_PATH, L"%ls\\SpeedForceLauncher.exe", g.app);
    swprintf(game, MAX_PATH, L"%ls\\SpeedForce.exe", g.app);
    CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    if (SUCCEEDED(SHGetKnownFolderPath(&FOLDERID_Programs, 0, NULL, &progs))) {
        swprintf(dir, MAX_PATH, L"%ls\\Speed Force", progs);
        CreateDirectoryW(dir, NULL);
        swprintf(lnk, MAX_PATH, L"%ls\\Speed Force.lnk", dir);
        shortcut(lnk, tgt, L"Speed Force launcher: settings, updates and Play");
        swprintf(lnk, MAX_PATH, L"%ls\\Speed Force (game only).lnk", dir);
        shortcut(lnk, game, L"Justice League Heroes - Speed Force");
        CoTaskMemFree(progs);
    }
    if (g.desktop && SUCCEEDED(SHGetKnownFolderPath(&FOLDERID_Desktop, 0, NULL, &desk))) {
        swprintf(lnk, MAX_PATH, L"%ls\\Speed Force.lnk", desk);
        shortcut(lnk, tgt, L"Speed Force launcher: settings, updates and Play");
        CoTaskMemFree(desk);
    }
    if (RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SpeedForce", 0,
                        NULL, 0, KEY_WRITE, NULL, &k, NULL) == ERROR_SUCCESS) {
        wchar_t un[MAX_PATH * 2];
        DWORD one = 1, kb = 5u * 1024 * 1024;
        swprintf(un, MAX_PATH * 2, L"\"%ls\" /uninstall", tgt);
#define SETS(n, v) RegSetValueExW(k, n, 0, REG_SZ, (const BYTE *)(v), (DWORD)((wcslen(v) + 1) * sizeof(wchar_t)))
        SETS(L"DisplayName", L"Speed Force");
        SETS(L"DisplayVersion", SF_VERSION_W);
        SETS(L"Publisher", L"Speed Force contributors");
        SETS(L"DisplayIcon", game);
        SETS(L"InstallLocation", g.app);
        SETS(L"UninstallString", un);
        SETS(L"URLInfoAbout", L"https://github.com/GhostDucky13/Speed-Force-Justice-League-Heroes-Windows-Recompilation");
        RegSetValueExW(k, L"NoModify", 0, REG_DWORD, (const BYTE *)&one, 4);
        RegSetValueExW(k, L"NoRepair", 0, REG_DWORD, (const BYTE *)&one, 4);
        RegSetValueExW(k, L"EstimatedSize", 0, REG_DWORD, (const BYTE *)&kb, 4);
#undef SETS
        RegCloseKey(k);
    }
}

/* ---------------------------------------------------------------- the build thread */
static DWORD WINAPI build_thread(void *arg)
{
    wchar_t xbox[MAX_PATH], psp[MAX_PATH], saves[MAX_PATH] = L"", cmd[4096], py[MAX_PATH];
    SECURITY_ATTRIBUTES sa = {sizeof sa, NULL, TRUE};
    HANDLE rd, wr;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    DWORD code = 1;
    (void)arg;
    wcscpy(xbox, (const wchar_t *)GetPropW(ui.wnd, L"xbox"));
    wcscpy(psp, (const wchar_t *)GetPropW(ui.wnd, L"psp"));
    if (GetPropW(ui.wnd, L"saves"))
        wcscpy(saves, (const wchar_t *)GetPropW(ui.wnd, L"saves"));

    if (!mkdirs(g.app)) {
        swprintf(g.error, 512, L"Can't create %ls.", g.app);
        PostMessageW(ui.wnd, WM_APP_DONE, 1, 0);
        return 0;
    }
    if (!unpack()) {
        PostMessageW(ui.wnd, WM_APP_DONE, g.stop ? 2 : 1, 0);
        return 0;
    }
    PostMessageW(ui.wnd, WM_APP_UNPACK, 1001, 0);   /* step 1 finished */

    swprintf(py, MAX_PATH, L"%ls\\_build\\python\\python.exe", g.app);
    swprintf(cmd, 4096, L"\"%ls\" -u \"%ls\\_build\\setup\\sf_install.py\" --xbox \"%ls\" --psp \"%ls\" --app \"%ls\"%ls%ls%ls",
             py, g.app, xbox, psp, g.app, saves[0] ? L" --saves \"" : L"", saves, saves[0] ? L"\"" : L"");
    CreatePipe(&rd, &wr, &sa, 0);
    SetHandleInformation(rd, HANDLE_FLAG_INHERIT, 0);
    memset(&si, 0, sizeof si);
    si.cb = sizeof si;
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = wr;
    si.hStdError = wr;
    g.job = CreateJobObjectW(NULL, NULL);
    {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION li;
        memset(&li, 0, sizeof li);
        li.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(g.job, JobObjectExtendedLimitInformation, &li, sizeof li);
    }
    if (!CreateProcessW(NULL, cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW | CREATE_SUSPENDED, NULL, g.app, &si, &pi)) {
        wcscpy(g.error, L"The build tools could not be started.");
        CloseHandle(rd);
        CloseHandle(wr);
        PostMessageW(ui.wnd, WM_APP_DONE, 1, 0);
        return 0;
    }
    AssignProcessToJobObject(g.job, pi.hProcess);
    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);
    CloseHandle(wr);
    g.proc = pi.hProcess;
    {
        char buf[4096], line[4096];
        size_t ln = 0;
        DWORD n, i;
        while (ReadFile(rd, buf, sizeof buf, &n, NULL) && n) {
            for (i = 0; i < n; i++) {
                if (buf[i] == '\n' || ln + 1 >= sizeof line) {
                    line[ln] = 0;
                    if (ln && line[ln - 1] == '\r') line[--ln] = 0;
                    post_line(line);
                    ln = 0;
                } else {
                    line[ln++] = buf[i];
                }
            }
        }
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(rd);
    if (code == 0 && !g.stop)
        finish_install();
    PostMessageW(ui.wnd, WM_APP_DONE, g.stop ? 2 : (code ? 1 : 0), 0);
    return 0;
}

static void start_build(void)
{
    static wchar_t xbox[MAX_PATH], psp[MAX_PATH], saves[MAX_PATH];
    int i;
    get_text(g.e_dir, g.app);
    get_text(g.e_xbox, xbox);
    get_text(g.e_psp, psp);
    get_text(g.e_saves, saves);
    SetPropW(ui.wnd, L"xbox", xbox);
    SetPropW(ui.wnd, L"psp", psp);
    SetPropW(ui.wnd, L"saves", g.saves_on && saves[0] ? saves : NULL);
    g.page = P_BUILD;
    g.building = 1;
    g.failed = g.cancelled = 0;
    g.stop = 0;
    g.error[0] = g.detail[0] = 0;
    g.step = 0;
    g.frac = 0;
    g.t0 = now_s();
    for (i = 0; i <= NSTEPS; i++) g.step_t0[i] = 0;
    for (i = 0; i < NSTEPS; i++) g.step_dur[i] = 0;
    g.step_t0[0] = g.t0;
    wcscpy(g.detail, L"Unpacking the compiler, Python and the Speed Force sources");
    SetTimer(ui.wnd, 1, 40, NULL);
    CloseHandle(CreateThread(NULL, 0, build_thread, NULL, 0, NULL));
}

static void set_step(int s)
{
    double t = now_s();
    int i;
    if (s <= g.step) return;
    for (i = g.step; i < s && i < NSTEPS; i++) {
        if (g.step_t0[i] == 0) g.step_t0[i] = t;
        g.step_dur[i] = t - g.step_t0[i];
    }
    g.step = s;
    if (s < NSTEPS) g.step_t0[s] = t;
    g.detail[0] = 0;
}

static void on_line(wchar_t *w)
{
    if (w[0] == L'@' && w[1] == L'@') {
        wchar_t *bar = wcschr(w, L'|');
        int pm = _wtoi(w + 2);
        g.frac = 0.05 + 0.95 * pm / 1000.0;
        if (bar && bar[1]) {
            const wchar_t *t = bar + 1;
            if (!wcsncmp(t, L"Step ", 5)) {
                int n = _wtoi(t + 5);
                if (n >= 1 && n <= 8) set_step(n);
            } else if (wcscmp(t, L"Done")) {
                wcsncpy(g.detail, t, 255);
            }
        }
        free(w);
        InvalidateRect(ui.wnd, NULL, FALSE);
        return;
    }
    {
        const wchar_t *t = w;
        if (wcslen(t) > 9 && t[2] == L':' && t[5] == L':') t += 9;
        while (*t == L' ') t++;
        if (!wcsncmp(t, L"ERROR:", 6)) {
            const wchar_t *e = t + 6;
            while (*e == L' ') e++;
            wcsncpy(g.error, e, 511);
        }
        if (*t != L'>')
            log_add(w);
    }
    free(w);
}

/* ---------------------------------------------------------------- painting */
static void paint_header(void)
{
    static const wchar_t *const names[3] = {L"Game files", L"Options", L"Build"};
    int i, x = 600;
    RECT r;
    if (g.logo) ui_image(g.logo, R(40, 26, 56, 56));
    ui_text(R(110, 24, 440, 36), L"Speed Force Builder", ui.f_title, C_TEXT, DT_SINGLELINE);
    ui_text(R(112, 62, 470, 20), L"Justice League Heroes, native on Windows, built from your own discs.", ui.f_small, C_SUB,
            DT_SINGLELINE);
    /* stepper */
    r = R(x, 34, 340, 40);
    ui_round(r, 20, C_BG2, C_BORDER);
    for (i = 0; i < 3; i++) {
        int cur = g.page == P_DONE ? ((g.failed || g.cancelled) ? 2 : 3) : g.page;
        int state = i < cur ? 1 : (i == cur ? 2 : 0);
        RECT pill = R(x + 6 + i * 111, 39, 106, 30), tr = pill;
        if (state == 2) ui_round(pill, 15, C_CARD2, 0);
        if (state == 1) {
            ui_circle((float)S(x + 22 + i * 111), (float)S(54), SF(9), RGBA(58, 210, 159, 40), 0, 0);
            ui_line(SF(x + 18 + i * 111), SF(54), SF(x + 21 + i * 111), SF(57), C_OK, SF(1.8f));
            ui_line(SF(x + 21 + i * 111), SF(57), SF(x + 26 + i * 111), SF(51), C_OK, SF(1.8f));
        } else {
            wchar_t n[4];
            ui_circle((float)S(x + 22 + i * 111), (float)S(54), SF(9), state == 2 ? C_ACCENT : C_CARD2, 0, 0);
            swprintf(n, 4, L"%d", i + 1);
            ui_text(R(x + 13 + i * 111, 45, 18, 18), n, ui.f_small, state == 2 ? RGBA(18, 20, 30, 255) : C_SUB,
                    DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }
        tr.left = S(x + 36 + i * 111);
        ui_text(tr, names[i], ui.f_small, state == 0 ? C_SUB : C_TEXT, DT_VCENTER | DT_SINGLELINE);
    }
}

static void check_line(int x, int y, int ok, const wchar_t *msg, int warn)
{
    ui_status_icon(S(x + 10), S(y + 10), ok ? 1 : (warn ? 4 : 3), 0);
    ui_text(R(x + 28, y, 760, 20), msg, ui.f_small, ok ? C_SUB : (warn ? C_ACCENT : C_BAD), DT_SINGLELINE | DT_VCENTER);
}

static void input_row(int x, int y, const wchar_t *label, HWND e, RECT *box, int browse_id, int enabled)
{
    ui_text(R(x, y, 600, 20), label, ui.f_bold, enabled ? C_TEXT : C_DIM, DT_SINGLELINE);
    *box = R(x, y + 26, 700, 40);
    ui_input_box(*box, GetFocus() == e);
    ui_button(R(x + 712, y + 26, 108, 40), browse_id, L"Browse", 0, enabled);
}

static void paint_files(void)
{
    RECT card = R(40, 104, 900, 452);
    ui_round(card, 12, C_CARD, C_BORDER);
    input_row(64, 124, L"Install folder", g.e_dir, &g.box_dir, B_DIR, 1);
    check_line(64, 196, g.ok_dir, g.msg_dir, g.old_install);
    if (g.msg_space[0]) check_line(64, 220, g.ok_space, g.msg_space, 0);
    input_row(64, 260, L"Your Xbox disc image", g.e_xbox, &g.box_xbox, B_XBOX, 1);
    check_line(64, 332, g.ok_xbox, g.msg_xbox, 0);
    input_row(64, 372, L"Your PSP disc image", g.e_psp, &g.box_psp, B_PSP, 1);
    check_line(64, 444, g.ok_psp, g.msg_psp, 0);
    ui_text(R(64, 488, 850, 60),
            L"This project contains no game files and no game code. Speed Force reads your own dumps (it never "
            L"changes them) and builds the game on this PC. Speed Force is built from the Xbox version, with the "
            L"extra characters and levels taken from the PSP version.",
            ui.f_small, C_DIM, DT_WORDBREAK);
    ui_text(R(40, 590, 400, 20), L"Builder v" SF_VERSION_W, ui.f_small, C_DIM, DT_SINGLELINE | DT_VCENTER);
    ui_button(R(780, 576, 160, 44), B_NEXT, L"Next", 1, g.ok_dir && g.ok_space && g.ok_xbox && g.ok_psp);
}

static void paint_options(void)
{
    RECT card = R(40, 104, 900, 250);
    ui_round(card, 12, C_CARD, C_BORDER);
    ui_text(R(64, 122, 600, 26), L"Your Xbox saves (optional)", ui.f_h2, C_TEXT, DT_SINGLELINE);
    ui_check(R(64, 156, 500, 28), C_SAVES, L"I have saves from an Xbox to bring over", g.saves_on);
    input_row(64, 192, L"Saves folder", g.e_saves, &g.box_saves, B_SAVES, g.saves_on);
    ui_text(R(64, 286, 840, 60),
            L"Choose the folder you copied from your Xbox (UDATA\\57520001, or a folder that holds it). Completed "
            L"saves work too: they start Episode 1 the Chapter Select way. Saves already on this PC are never "
            L"overwritten.", ui.f_small, C_SUB, DT_WORDBREAK);

    card = R(40, 370, 900, 182);
    ui_round(card, 12, C_CARD, C_BORDER);
    ui_text(R(64, 388, 600, 26), L"Shortcuts", ui.f_h2, C_TEXT, DT_SINGLELINE);
    ui_check(R(64, 422, 500, 28), C_DESKTOP, L"Put a Speed Force shortcut on the desktop", g.desktop);
    ui_text(R(64, 458, 840, 80),
            L"The Start menu gets \"Speed Force\" (the launcher: settings, updates and Play) and \"Speed Force "
            L"(game only)\", which starts the game directly. The build takes about 20-40 minutes; you can keep "
            L"using your PC.", ui.f_small, C_SUB, DT_WORDBREAK);
    ui_button(R(40, 576, 140, 44), B_BACK, L"Back", 0, 1);
    ui_button(R(740, 576, 200, 44), B_BUILD, L"Build Speed Force", 1,
              !g.saves_on || GetWindowTextLengthW(g.e_saves) > 0);
}

static double eta_seconds(void)
{
    double t = now_s(), ratio = 1, done_exp = 0, done_act = 0, rem = 0;
    int i;
    for (i = 0; i < g.step && i < NSTEPS; i++) {
        done_exp += k_expect[i];
        done_act += g.step_dur[i];
    }
    if (done_exp > 120) ratio = done_act / done_exp;
    if (ratio < 0.4) ratio = 0.4;
    if (ratio > 3) ratio = 3;
    for (i = g.step; i < NSTEPS; i++) {
        double e = k_expect[i] * ratio;
        if (i == g.step) {
            e -= t - g.step_t0[i];
            if (e < 15) e = 15;
        }
        rem += e;
    }
    return rem;
}

static void paint_build(void)
{
    RECT card = R(40, 104, 900, 452);
    wchar_t t[160], a[32];
    int i, done = g.page == P_DONE;
    double el = (done ? g.step_t0[NSTEPS] : now_s()) - g.t0;

    ui_round(card, 12, C_CARD, C_BORDER);
    if (done && !g.failed && !g.cancelled) {
        ui_status_icon(S(76), S(142), 1, 0);
        ui_text(R(100, 124, 600, 36), L"Speed Force is ready", ui.f_h1, C_TEXT, DT_SINGLELINE);
        ui_fmt_time(a, 32, el);
        swprintf(t, 160, L"Built and installed in %ls. Have fun!", a);
        ui_text(R(100, 160, 600, 20), t, ui.f_small, C_SUB, DT_SINGLELINE);
    } else if (done) {
        ui_status_icon(S(76), S(142), g.cancelled ? 4 : 3, 0);
        ui_text(R(100, 124, 600, 36), g.cancelled ? L"The build was cancelled" : L"The build stopped", ui.f_h1, C_TEXT,
                DT_SINGLELINE);
        ui_text(R(100, 160, 760, 40), g.cancelled ? L"Nothing was finished. You can start it again." :
                (g.error[0] ? g.error : L"See the log for the reason."), ui.f_small, g.cancelled ? C_SUB : C_BAD,
                DT_WORDBREAK);
    } else {
        ui_text(R(64, 124, 600, 36), L"Building Speed Force " SF_VERSION_W, ui.f_h1, C_TEXT, DT_SINGLELINE);
        ui_text(R(64, 160, 600, 20), L"You can keep using your PC. Closing this window stops the build.", ui.f_small,
                C_SUB, DT_SINGLELINE);
        swprintf(t, 160, L"%d%%", (int)(g.frac * 100));
        ui_text(R(700, 112, 216, 52), t, ui.f_huge, C_TEXT, DT_RIGHT | DT_SINGLELINE);
        if (g.frac > 0.02) {
            ui_fmt_time(a, 32, eta_seconds());
            swprintf(t, 160, L"About %ls left", a);
        } else {
            wcscpy(t, L"Estimating...");
        }
        ui_text(R(600, 162, 316, 20), t, ui.f_small, C_SUB, DT_RIGHT | DT_SINGLELINE);
    }
    ui_progress(R(64, 196, 852, 8), done && !g.failed && !g.cancelled ? 1.0 : g.frac, C_ACCENT2, C_ACCENT);

    if (g.details) {
        ShowWindow(g.e_log, SW_SHOW);
        SetWindowPos(g.e_log, NULL, S(64), S(222), S(852), S(316), SWP_NOZORDER);
    } else {
        ShowWindow(g.e_log, SW_HIDE);
        ui_round(R(64, 222, 852, 316), 10, C_BG2, C_BORDER);
        for (i = 0; i < NSTEPS; i++) {
            int y = 226 + i * 34, state;
            double d;
            if (i < g.step) state = 1;
            else if (i == g.step && !done) state = 2;
            else if (i == g.step && done && (g.failed || g.cancelled)) state = g.cancelled ? 4 : 3;
            else state = 0;
            if (i > 0) {
                RECT sep = R(80, y, 820, 1);
                HBRUSH b = CreateSolidBrush(ui_cr(RGBA(30, 39, 64, 255)));
                FillRect(ui.dc, &sep, b);
                DeleteObject(b);
            }
            ui_status_icon(S(90), S(y + 17), state, g.spin);
            ui_text(R(112, y, 300, 34), k_steps[i], state == 2 ? ui.f_bold : ui.f_body, state == 0 ? C_SUB : C_TEXT,
                    DT_VCENTER | DT_SINGLELINE);
            t[0] = 0;
            if (state == 1) wcscpy(t, L"Done");
            else if (state == 2) wcsncpy(t, g.detail, 159);
            else if (state == 3) wcscpy(t, L"Stopped");
            else if (state == 4) wcscpy(t, L"Cancelled");
            t[159] = 0;
            ui_text(R(400, y, 380, 34), t, ui.f_small, state == 3 ? C_BAD : C_SUB, DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
            d = state == 1 ? g.step_dur[i] : (state >= 2 ? (done ? g.step_t0[NSTEPS] : now_s()) - g.step_t0[i] : 0);
            if (state != 0) {
                ui_fmt_time(a, 32, d);
                ui_text(R(780, y, 120, 34), a, ui.f_small, state == 2 ? C_TEXT : C_SUB, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
            }
        }
    }
    ui_link(R(44, 584, 160, 28), B_DETAILS, g.details ? L"Hide details" : L"Show details");
    if (!done) {
        ui_button(R(800, 576, 140, 44), B_CANCEL, L"Cancel", 0, 1);
    } else if (!g.failed && !g.cancelled) {
        ui_button(R(420, 576, 150, 44), B_FOLDER, L"Open folder", 2, 1);
        ui_button(R(580, 576, 170, 44), B_LAUNCHER, L"Open launcher", 0, 1);
        ui_button(R(760, 576, 180, 44), B_PLAY, L"Play", 1, 1);
    } else {
        ui_button(R(480, 576, 140, 44), B_LOG, L"Open log", 0, 1);
        ui_button(R(630, 576, 150, 44), B_RETRY, L"Try again", 0, 1);
        ui_button(R(790, 576, 150, 44), B_CLOSE, L"Close", 1, 1);
    }
}

static void layout_edits(void)
{
    ShowWindow(g.e_dir, g.page == P_FILES ? SW_SHOW : SW_HIDE);
    ShowWindow(g.e_xbox, g.page == P_FILES ? SW_SHOW : SW_HIDE);
    ShowWindow(g.e_psp, g.page == P_FILES ? SW_SHOW : SW_HIDE);
    ShowWindow(g.e_saves, g.page == P_OPTIONS ? SW_SHOW : SW_HIDE);
    EnableWindow(g.e_saves, g.saves_on);
    if (g.page != P_BUILD && g.page != P_DONE) ShowWindow(g.e_log, SW_HIDE);
    ui_place_edit(g.e_dir, R(64, 150, 700, 40));
    ui_place_edit(g.e_xbox, R(64, 286, 700, 40));
    ui_place_edit(g.e_psp, R(64, 398, 700, 40));
    ui_place_edit(g.e_saves, R(64, 218, 700, 40));
}

static void paint(void)
{
    UiPaint p;
    ui_begin(&p);
    paint_header();
    if (g.page == P_FILES) paint_files();
    else if (g.page == P_OPTIONS) paint_options();
    else paint_build();
    ui_end(&p);
}

static void go(int page)
{
    g.page = page;
    layout_edits();
    InvalidateRect(ui.wnd, NULL, FALSE);
}

static void open_path(const wchar_t *rel)
{
    wchar_t p[MAX_PATH];
    swprintf(p, MAX_PATH, rel[0] ? L"%ls\\%ls" : L"%ls", g.app, rel);
    ShellExecuteW(ui.wnd, L"open", p, NULL, g.app, SW_SHOWNORMAL);
}

static void command(int id)
{
    wchar_t p[MAX_PATH];
    switch (id) {
    case B_DIR:
        get_text(g.e_dir, p);
        if (ui_pick(p, 1, L"Where to install Speed Force", NULL, NULL)) {
            size_t n = wcslen(p);
            if (n < 12 || _wcsicmp(p + n - 12, L"\\Speed Force"))
                wcscat(p, L"\\Speed Force");
            SetWindowTextW(g.e_dir, p);
        }
        break;
    case B_XBOX:
        if (ui_pick(p, 0, L"Your Xbox disc image", L"Disc images (*.iso, *.xiso)", L"*.iso;*.xiso"))
            SetWindowTextW(g.e_xbox, p);
        break;
    case B_PSP:
        if (ui_pick(p, 0, L"Your PSP disc image", L"Disc images (*.iso)", L"*.iso"))
            SetWindowTextW(g.e_psp, p);
        break;
    case B_SAVES:
        if (ui_pick(p, 1, L"The folder with your Xbox saves (UDATA\\57520001)", NULL, NULL))
            SetWindowTextW(g.e_saves, p);
        break;
    case C_SAVES: g.saves_on = !g.saves_on; layout_edits(); break;
    case C_DESKTOP: g.desktop = !g.desktop; break;
    case B_NEXT: go(P_OPTIONS); break;
    case B_BACK: go(P_FILES); break;
    case B_BUILD: case B_RETRY: start_build(); layout_edits(); break;
    case B_CANCEL:
        if (MessageBoxW(ui.wnd, L"Stop the build? You can start it again later.", L"Speed Force",
                        MB_YESNO | MB_ICONQUESTION) == IDYES) {
            g.stop = 1;
            if (g.job) TerminateJobObject(g.job, 2);
        }
        break;
    case B_DETAILS:
        g.details = !g.details;
        if (g.details) {
            SetWindowTextW(g.e_log, g.log ? g.log : L"");
            SendMessageW(g.e_log, EM_SETSEL, (WPARAM)-1, (LPARAM)-1);
            SendMessageW(g.e_log, EM_SCROLLCARET, 0, 0);
        }
        break;
    case B_PLAY: open_path(L"SpeedForce.exe"); PostMessageW(ui.wnd, WM_CLOSE, 0, 0); break;
    case B_LAUNCHER: open_path(L"SpeedForceLauncher.exe"); PostMessageW(ui.wnd, WM_CLOSE, 0, 0); break;
    case B_FOLDER: open_path(L""); break;
    case B_LOG: open_path(L"install.log"); break;
    case B_CLOSE: PostMessageW(ui.wnd, WM_CLOSE, 0, 0); break;
    }
    InvalidateRect(ui.wnd, NULL, FALSE);
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    switch (m) {
    case WM_PAINT: paint(); return 0;
    case WM_ERASEBKGND: return 1;
    case WM_MOUSEMOVE: case WM_MOUSELEAVE: case WM_LBUTTONDOWN: case WM_LBUTTONUP: {
        int k = 0, id = ui_mouse(m, lp, &k);
        if (m == WM_LBUTTONDOWN) SetFocus(h);
        if (id) command(id);
        return 0;
    }
    case WM_SETCURSOR:
        if (LOWORD(lp) == HTCLIENT) return TRUE;
        break;
    case WM_COMMAND:
        if (HIWORD(wp) == EN_CHANGE && (LOWORD(wp) == ID_DIR || LOWORD(wp) == ID_XBOX || LOWORD(wp) == ID_PSP))
            validate();
        if (HIWORD(wp) == EN_CHANGE && LOWORD(wp) == ID_SAVES) InvalidateRect(h, NULL, FALSE);
        if (HIWORD(wp) == EN_SETFOCUS || HIWORD(wp) == EN_KILLFOCUS) InvalidateRect(h, NULL, FALSE);
        return 0;
    case WM_CTLCOLOREDIT: case WM_CTLCOLORSTATIC:
        SetTextColor((HDC)wp, ui_cr(C_TEXT));
        SetBkColor((HDC)wp, ui_cr((HWND)lp == g.e_log ? C_BG2 : C_INPUT));
        {
            static HBRUSH bg2;
            if (!bg2) bg2 = CreateSolidBrush(ui_cr(C_BG2));
            return (LRESULT)((HWND)lp == g.e_log ? bg2 : ui.input_brush);
        }
    case WM_TIMER:
        g.spin = (g.spin + 12) % 360;
        InvalidateRect(h, NULL, FALSE);
        return 0;
    case WM_APP_LINE: on_line((wchar_t *)lp); return 0;
    case WM_APP_UNPACK:
        if (wp > 1000) {
            set_step(1);
        } else {
            wchar_t t[64];
            g.frac = 0.05 * (double)wp / 1000.0;
            swprintf(t, 64, L"%d%%", (int)(wp / 10));
            wcscpy(g.detail, t);
        }
        return 0;
    case WM_APP_DONE:
        g.building = 0;
        g.failed = wp == 1;
        g.cancelled = wp == 2;
        g.step_t0[NSTEPS] = now_s();
        if (wp == 0) {
            set_step(NSTEPS);
            g.frac = 1;
        } else if (g.step < NSTEPS && g.step_t0[g.step]) {
            g.step_dur[g.step] = now_s() - g.step_t0[g.step];
        }
        if (g.job) { CloseHandle(g.job); g.job = NULL; }
        if (wp == 1 && g.error[0]) {
            wchar_t t[600];
            swprintf(t, 600, L"ERROR: %ls", g.error);
            log_add(t);
        }
        KillTimer(h, 1);
        go(P_DONE);
        if (wp == 0) FlashWindow(h, TRUE);
        return 0;
    case WM_DPICHANGED: {
        RECT *r = (RECT *)lp;
        ui.dpi = HIWORD(wp);
        ui_fonts();
        SendMessageW(g.e_dir, WM_SETFONT, (WPARAM)ui.f_body, TRUE);
        SendMessageW(g.e_xbox, WM_SETFONT, (WPARAM)ui.f_body, TRUE);
        SendMessageW(g.e_psp, WM_SETFONT, (WPARAM)ui.f_body, TRUE);
        SendMessageW(g.e_saves, WM_SETFONT, (WPARAM)ui.f_body, TRUE);
        SendMessageW(g.e_log, WM_SETFONT, (WPARAM)ui.f_mono, TRUE);
        SetWindowPos(h, NULL, r->left, r->top, r->right - r->left, r->bottom - r->top, SWP_NOZORDER);
        layout_edits();
        return 0;
    }
    case WM_CLOSE:
        if (g.building) {
            if (MessageBoxW(h, L"The build is still running. Stop it and close?", L"Speed Force",
                            MB_YESNO | MB_ICONQUESTION) != IDYES)
                return 0;
            g.stop = 1;
            if (g.job) TerminateJobObject(g.job, 2);
        }
        DestroyWindow(h);
        return 0;
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
    int dpi;
    wchar_t def[MAX_PATH];
    (void)prev;
    (void)cmdline;
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = wndproc;
    wc.hInstance = inst;
    wc.hIcon = LoadIconW(inst, MAKEINTRESOURCEW(1));
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = L"SpeedForceBuilder";
    RegisterClassW(&wc);
    dpi = (int)GetDpiForSystem();
    r.left = r.top = 0;
    r.right = MulDiv(980, dpi, 96);
    r.bottom = MulDiv(640, dpi, 96);
    AdjustWindowRectExForDpi(&r, style, FALSE, 0, (UINT)dpi);
    ui.wnd = CreateWindowW(L"SpeedForceBuilder", L"Speed Force Builder " SF_VERSION_W, style, CW_USEDEFAULT, CW_USEDEFAULT,
                           r.right - r.left, r.bottom - r.top, NULL, NULL, inst, NULL);
    ui_init(ui.wnd);
    if (ui.dpi != dpi) {   /* the window opened on a monitor with another scale */
        r.left = r.top = 0;
        r.right = S(980);
        r.bottom = S(640);
        AdjustWindowRectExForDpi(&r, style, FALSE, 0, (UINT)ui.dpi);
        SetWindowPos(ui.wnd, NULL, 0, 0, r.right - r.left, r.bottom - r.top, SWP_NOMOVE | SWP_NOZORDER);
    }
    g.logo = ui_png(101);
    g.desktop = 1;
    g.e_dir = ui_edit(ID_DIR);
    g.e_xbox = ui_edit(ID_XBOX);
    g.e_psp = ui_edit(ID_PSP);
    g.e_saves = ui_edit(ID_SAVES);
    g.e_log = CreateWindowExW(0, L"EDIT", L"", WS_CHILD | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL,
                              0, 0, 10, 10, ui.wnd, (HMENU)300, inst, NULL);
    SendMessageW(g.e_log, WM_SETFONT, (WPARAM)ui.f_mono, TRUE);
    SendMessageW(g.e_log, EM_SETLIMITTEXT, 0, 0);
    SetWindowTheme(g.e_log, L"DarkMode_Explorer", NULL);
    ExpandEnvironmentStringsW(L"%LOCALAPPDATA%\\Programs\\Speed Force", def, MAX_PATH);
    SetWindowTextW(g.e_dir, def);
    {   /* scripted: SpeedForce-Setup.exe /xbox <iso> /psp <iso> [/dir <folder>] [/saves <folder>] */
        int argc, i;
        wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
        for (i = 1; argv && i + 1 < argc; i++) {
            if (!_wcsicmp(argv[i], L"/xbox")) SetWindowTextW(g.e_xbox, argv[++i]);
            else if (!_wcsicmp(argv[i], L"/psp")) SetWindowTextW(g.e_psp, argv[++i]);
            else if (!_wcsicmp(argv[i], L"/dir")) SetWindowTextW(g.e_dir, argv[++i]);
            else if (!_wcsicmp(argv[i], L"/saves")) { SetWindowTextW(g.e_saves, argv[++i]); g.saves_on = 1; }
        }
    }
    validate();
    go(P_FILES);
    ShowWindow(ui.wnd, show);
    UpdateWindow(ui.wnd);
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        if (!IsDialogMessageW(ui.wnd, &msg)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    return (int)msg.wParam;
}
