/*
 * netplay.c - see netplay.h.
 */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <mmsystem.h>
#include <ole2.h>
#include <oleauto.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "netplay.h"

extern ptrdiff_t g_xbox_mem_offset;
extern uint32_t g_xbox_total_ram;
uint64_t xbox_GuestStateHashBytes(const void *p, size_t len);
void nv2a_overlay_toast(const char *fmt, ...);

#define RING 4096                       /* frames of input kept; > any delay */
#define MSG_INPUT 2
#define MSG_HASH  3
#define MSG_BYE   4
#define PROTOCOL  2

#pragma pack(push, 1)
typedef struct {
    uint8_t  type;
    uint8_t  pad[3];
    uint32_t frame;                     /* INPUT: the poll it is for; HASH: the poll hashed */
    uint8_t  data[20];                  /* INPUT: the report; HASH: u64 */
} Msg;
#pragma pack(pop)

static int s_started, s_player, s_delay = 8, s_hash_every = 300;
static SOCKET s_sock = INVALID_SOCKET;
static CRITICAL_SECTION s_lock;
static CONDITION_VARIABLE s_cv;
static uint8_t s_remote[RING][20];
static int64_t s_remote_upto = -1;      /* highest frame received from the other side */
static volatile LONG s_remote_gone, s_told_gone;
static uint8_t s_local[RING][20];
static uint32_t s_frame;                /* polls done */
static uint64_t s_my_hash[RING / 64], s_their_hash[RING / 64];
static uint32_t s_my_hash_at[RING / 64], s_their_hash_at[RING / 64];
static int s_desyncs, s_checks;
static FILE *s_log;
static uint64_t s_wait_us, s_waits;
static unsigned s_rtt_ms;
static LARGE_INTEGER s_freq;

static void say(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fputs("  [NETPLAY] ", stderr);
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr);
    fflush(stderr);
    va_end(ap);
}

static uint64_t now_us(void)
{
    LARGE_INTEGER t;
    if (!s_freq.QuadPart)
        QueryPerformanceFrequency(&s_freq);
    QueryPerformanceCounter(&t);
    return (uint64_t)(t.QuadPart * 1000000 / s_freq.QuadPart);
}

/* ---------------------------------------------------------------- the waiting window */

static HWND s_win, s_text;
static HANDLE s_win_ready;
static volatile LONG s_cancel, s_closing;
static wchar_t s_status_w[1024] = L"Starting...";

#define ID_CANCEL 101
#define WM_APP_TEXT (WM_APP + 1)

static LRESULT CALLBACK win_proc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    switch (m) {
    case WM_COMMAND:
        if (LOWORD(w) == ID_CANCEL)
            InterlockedExchange(&s_cancel, 1);
        return 0;
    case WM_CLOSE:
        if (!s_closing)
            InterlockedExchange(&s_cancel, 1);
        else
            DestroyWindow(h);
        return 0;
    case WM_APP_TEXT:
        SetWindowTextW(s_text, s_status_w);
        return 0;
    case WM_CTLCOLORSTATIC:
        SetBkMode((HDC)w, TRANSPARENT);
        return (LRESULT)GetSysColorBrush(COLOR_WINDOW);
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

static DWORD WINAPI win_thread(LPVOID unused)
{
    WNDCLASSW wc;
    MSG msg;
    HFONT font;
    HWND btn;
    RECT r;
    int sw = GetSystemMetrics(SM_CXSCREEN), sh = GetSystemMetrics(SM_CYSCREEN);
    (void)unused;
    memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = win_proc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"SpeedForceNetplay";
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = GetSysColorBrush(COLOR_WINDOW);
    wc.hIcon = LoadIconW(wc.hInstance, MAKEINTRESOURCEW(1));
    RegisterClassW(&wc);
    r.left = 0; r.top = 0; r.right = 520; r.bottom = 230;
    AdjustWindowRect(&r, WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU, FALSE);
    s_win = CreateWindowW(wc.lpszClassName, L"Speed Force - Online", WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
                          (sw - (r.right - r.left)) / 2, (sh - (r.bottom - r.top)) / 2,
                          r.right - r.left, r.bottom - r.top, NULL, NULL, wc.hInstance, NULL);
    font = CreateFontW(-16, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    s_text = CreateWindowW(L"STATIC", s_status_w, WS_CHILD | WS_VISIBLE, 20, 16, 480, 160, s_win, NULL,
                           wc.hInstance, NULL);
    btn = CreateWindowW(L"BUTTON", L"Cancel", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 400, 184, 100, 32, s_win,
                        (HMENU)(INT_PTR)ID_CANCEL, wc.hInstance, NULL);
    SendMessageW(s_text, WM_SETFONT, (WPARAM)font, TRUE);
    SendMessageW(btn, WM_SETFONT, (WPARAM)font, TRUE);
    ShowWindow(s_win, SW_SHOW);
    SetForegroundWindow(s_win);
    SetEvent(s_win_ready);
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    s_win = NULL;
    return 0;
}

void netplay_status(const char *utf8)
{
    say("%s", utf8);
    MultiByteToWideChar(CP_UTF8, 0, utf8, -1, s_status_w, 1024);
    if (s_win)
        PostMessageW(s_win, WM_APP_TEXT, 0, 0);
}

void netplay_close_window(void)
{
    if (s_win) {
        InterlockedExchange(&s_closing, 1);
        PostMessageW(s_win, WM_CLOSE, 0, 0);
    }
}

static void check_cancel(void)
{
    if (s_cancel) {
        say("cancelled by the player");
        ExitProcess(0);
    }
}

/* ---------------------------------------------------------------- UPnP (Windows' NATUPnP) */

/* The three interfaces, declared here: llvm-mingw has no natupnp.h. */
typedef struct IStaticPortMapping IStaticPortMapping;
typedef struct IStaticPortMappingCollection IStaticPortMappingCollection;
typedef struct IUPnPNAT IUPnPNAT;
typedef struct {
    HRESULT (STDMETHODCALLTYPE *QueryInterface)(IStaticPortMapping *, REFIID, void **);
    ULONG (STDMETHODCALLTYPE *AddRef)(IStaticPortMapping *);
    ULONG (STDMETHODCALLTYPE *Release)(IStaticPortMapping *);
    void *dispatch[4];
    HRESULT (STDMETHODCALLTYPE *get_ExternalIPAddress)(IStaticPortMapping *, BSTR *);
} IStaticPortMappingVtbl;
struct IStaticPortMapping { const IStaticPortMappingVtbl *lpVtbl; };
typedef struct {
    HRESULT (STDMETHODCALLTYPE *QueryInterface)(IStaticPortMappingCollection *, REFIID, void **);
    ULONG (STDMETHODCALLTYPE *AddRef)(IStaticPortMappingCollection *);
    ULONG (STDMETHODCALLTYPE *Release)(IStaticPortMappingCollection *);
    void *dispatch[4];
    void *get__NewEnum;
    HRESULT (STDMETHODCALLTYPE *get_Item)(IStaticPortMappingCollection *, long, BSTR, IStaticPortMapping **);
    HRESULT (STDMETHODCALLTYPE *get_Count)(IStaticPortMappingCollection *, long *);
    HRESULT (STDMETHODCALLTYPE *Remove)(IStaticPortMappingCollection *, long, BSTR);
    HRESULT (STDMETHODCALLTYPE *Add)(IStaticPortMappingCollection *, long, BSTR, long, BSTR, VARIANT_BOOL, BSTR,
                                     IStaticPortMapping **);
} IStaticPortMappingCollectionVtbl;
struct IStaticPortMappingCollection { const IStaticPortMappingCollectionVtbl *lpVtbl; };
typedef struct {
    HRESULT (STDMETHODCALLTYPE *QueryInterface)(IUPnPNAT *, REFIID, void **);
    ULONG (STDMETHODCALLTYPE *AddRef)(IUPnPNAT *);
    ULONG (STDMETHODCALLTYPE *Release)(IUPnPNAT *);
    void *dispatch[4];
    HRESULT (STDMETHODCALLTYPE *get_StaticPortMappingCollection)(IUPnPNAT *, IStaticPortMappingCollection **);
} IUPnPNATVtbl;
struct IUPnPNAT { const IUPnPNATVtbl *lpVtbl; };

static const GUID CLSID_UPnPNAT_ = {0xAE1E00AA, 0x3FD5, 0x403C, {0x8A, 0x27, 0x2B, 0xBD, 0xC3, 0x0C, 0xD0, 0xE1}};
static const GUID IID_IUPnPNAT_ = {0xB171C812, 0xCC76, 0x485A, {0x94, 0xD8, 0xB6, 0xB3, 0xA2, 0x79, 0x4E, 0x99}};

static IStaticPortMappingCollection *s_upnp_maps;
static long s_upnp_port;

/* This PC's address on its network (the one a route to the internet uses). */
static int local_ip(char *out, size_t n)
{
    SOCKET u = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    struct sockaddr_in a;
    int len = sizeof a;
    int ok = 0;
    if (u == INVALID_SOCKET)
        return 0;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_port = htons(53);
    a.sin_addr.s_addr = htonl(0x08080808);  /* nothing is sent: connect only picks the route */
    if (connect(u, (struct sockaddr *)&a, sizeof a) == 0 && getsockname(u, (struct sockaddr *)&a, &len) == 0) {
        inet_ntop(AF_INET, &a.sin_addr, out, (socklen_t)n);
        ok = 1;
    }
    closesocket(u);
    return ok;
}

/* Ask the router to forward the port to this PC. Fills public with the
 * router's internet address when it answers. */
static int upnp_open(int port, const char *lan, char *public_ip, size_t n)
{
    IUPnPNAT *nat = NULL;
    IStaticPortMappingCollection *maps = NULL;
    IStaticPortMapping *map = NULL;
    BSTR proto, client, desc, ext = NULL;
    wchar_t wlan[64];
    HRESULT hr;
    int ok = 0;

    if (FAILED(CoInitializeEx(NULL, COINIT_MULTITHREADED)) && FAILED(CoInitialize(NULL)))
        return 0;
    if (FAILED(CoCreateInstance(&CLSID_UPnPNAT_, NULL, CLSCTX_INPROC_SERVER, &IID_IUPnPNAT_, (void **)&nat)) || !nat)
        return 0;
    hr = nat->lpVtbl->get_StaticPortMappingCollection(nat, &maps);
    if (FAILED(hr) || !maps) {          /* no UPnP router answered */
        nat->lpVtbl->Release(nat);
        return 0;
    }
    MultiByteToWideChar(CP_UTF8, 0, lan, -1, wlan, 64);
    proto = SysAllocString(L"TCP");
    client = SysAllocString(wlan);
    desc = SysAllocString(L"Speed Force online");
    maps->lpVtbl->Remove(maps, port, proto);  /* an old one of ours */
    hr = maps->lpVtbl->Add(maps, port, proto, port, client, VARIANT_TRUE, desc, &map);
    if (SUCCEEDED(hr) && map) {
        ok = 1;
        if (SUCCEEDED(map->lpVtbl->get_ExternalIPAddress(map, &ext)) && ext) {
            WideCharToMultiByte(CP_UTF8, 0, ext, -1, public_ip, (int)n, NULL, NULL);
            SysFreeString(ext);
        }
        map->lpVtbl->Release(map);
        s_upnp_maps = maps;
        s_upnp_port = port;
    } else {
        maps->lpVtbl->Release(maps);
    }
    SysFreeString(proto);
    SysFreeString(client);
    SysFreeString(desc);
    nat->lpVtbl->Release(nat);
    return ok;
}

static void upnp_close(void)
{
    if (s_upnp_maps) {
        BSTR proto = SysAllocString(L"TCP");
        s_upnp_maps->lpVtbl->Remove(s_upnp_maps, s_upnp_port, proto);
        SysFreeString(proto);
        s_upnp_maps->lpVtbl->Release(s_upnp_maps);
        s_upnp_maps = NULL;
    }
}

/* ---------------------------------------------------------------- the link */

static int send_all(const void *p, int n)
{
    const char *c = (const char *)p;
    while (n > 0) {
        int k = send(s_sock, c, n, 0);
        if (k <= 0)
            return -1;
        c += k;
        n -= k;
    }
    return 0;
}

static int recv_all(void *p, int n)
{
    char *c = (char *)p;
    while (n > 0) {
        int k = recv(s_sock, c, n, 0);
        if (k <= 0)
            return -1;
        c += k;
        n -= k;
    }
    return 0;
}

int netplay_send_blob(const void *p, uint32_t n)
{
    if (send_all(&n, 4) || (n && send_all(p, (int)n)))
        return -1;
    return 0;
}

void *netplay_recv_blob(uint32_t *n)
{
    uint32_t len;
    char *p;
    if (recv_all(&len, 4) || len > (64u << 20))
        return NULL;
    p = (char *)malloc(len + 1);
    if (!p)
        return NULL;
    if (len && recv_all(p, (int)len)) {
        free(p);
        return NULL;
    }
    p[len] = 0;
    if (n)
        *n = len;
    return p;
}

/* Wait for a readable socket or the Cancel button, 250 ms at a time. */
static int wait_readable(SOCKET s, int seconds)
{
    int i;
    for (i = 0; seconds < 0 || i < seconds * 4; i++) {
        fd_set f;
        struct timeval tv = {0, 250000};
        check_cancel();
        FD_ZERO(&f);
        FD_SET(s, &f);
        if (select(0, &f, NULL, NULL, &tv) > 0)
            return 1;
    }
    return 0;
}

int netplay_is_host(void)
{
    return s_player == 0;
}

unsigned netplay_rtt_ms(void)
{
    return s_rtt_ms;
}

int netplay_delay_for_rtt(unsigned rtt_ms)
{
    /* one way, plus 40 ms for jitter, in 60 Hz polls, at least 4 */
    int d = (int)((rtt_ms / 2 + 40) * 60 + 999) / 1000;
    return d < 4 ? 4 : d > 30 ? 30 : d;
}

static void measure_rtt(void)
{
    if (s_player == 0) {
        unsigned best = 0xFFFFFFFFu;
        int i;
        for (i = 0; i < 8; i++) {
            uint64_t t0 = now_us(), back;
            uint32_t n;
            void *r;
            netplay_send_blob(&t0, 8);
            r = netplay_recv_blob(&n);
            if (!r)
                return;
            memcpy(&back, r, 8);
            free(r);
            if ((unsigned)((now_us() - back) / 1000) < best)
                best = (unsigned)((now_us() - back) / 1000);
        }
        s_rtt_ms = best;
        netplay_send_blob(&s_rtt_ms, 4);
    } else {
        int i;
        for (i = 0; i < 8; i++) {
            uint32_t n;
            void *r = netplay_recv_blob(&n);
            if (!r)
                return;
            netplay_send_blob(r, n);
            free(r);
        }
        {
            uint32_t n;
            void *r = netplay_recv_blob(&n);
            if (r) {
                memcpy(&s_rtt_ms, r, 4);
                free(r);
            }
        }
    }
}

int netplay_connect(const char *spec, char *err, size_t errn)
{
    WSADATA wsa;
    struct addrinfo hints, *res = NULL;
    char host[256] = "", port[16] = "", msg[1024];
    int one = 1;

    InitializeCriticalSection(&s_lock);
    InitializeConditionVariable(&s_cv);
    s_win_ready = CreateEventW(NULL, TRUE, FALSE, NULL);
    CloseHandle(CreateThread(NULL, 0, win_thread, NULL, 0, NULL));
    WaitForSingleObject(s_win_ready, 5000);
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        snprintf(err, errn, "Windows networking could not start.");
        return -1;
    }
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    if (!strncmp(spec, "host:", 5)) {
        const char *a = spec + 5, *colon = strrchr(a, ':');
        char lan[64] = "", pub[64] = "";
        SOCKET ls;
        int upnp = 0;
        s_player = 0;
        if (colon) {                    /* host:<address>:<port> listens on that address only */
            snprintf(host, sizeof host, "%.*s", (int)(colon - a), a);
            snprintf(port, sizeof port, "%s", colon + 1);
        } else {
            snprintf(port, sizeof port, "%s", a);
        }
        hints.ai_flags = AI_PASSIVE;
        if (getaddrinfo(host[0] ? host : NULL, port, &hints, &res) != 0) {
            snprintf(err, errn, "Port %s isn't valid.", port);
            return -1;
        }
        ls = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
        if (ls == INVALID_SOCKET || bind(ls, res->ai_addr, (int)res->ai_addrlen) != 0 || listen(ls, 1) != 0) {
            snprintf(err, errn, "Port %s is already in use on this PC (error %d). Pick another port.", port,
                     WSAGetLastError());
            freeaddrinfo(res);
            return -1;
        }
        freeaddrinfo(res);
        local_ip(lan, sizeof lan);
        if (!host[0] || strcmp(host, "127.0.0.1")) {
            netplay_status("Hosting. Asking your router to open the port...");
            upnp = upnp_open(atoi(port), lan, pub, sizeof pub);
        }
        snprintf(msg, sizeof msg,
                 "Hosting on port %s. Waiting for player 2 to join...\n\n"
                 "Player 2 joins with:\n"
                 "    %s%s%s   (over the internet)\n"
                 "    %s:%s   (on the same network)\n\n%s",
                 port, pub[0] ? pub : "your internet address", ":", port, lan[0] ? lan : "this PC's address", port,
                 upnp ? "Your router opened the port automatically."
                      : "If player 2 can't connect: forward this TCP port on your router\nto this PC, or both use Tailscale or ZeroTier and join with its address.");
        netplay_status(msg);
        if (!wait_readable(ls, -1)) {
            closesocket(ls);
            snprintf(err, errn, "Nobody joined.");
            return -1;
        }
        s_sock = accept(ls, NULL, NULL);
        closesocket(ls);
    } else if (!strncmp(spec, "join:", 5)) {
        const char *a = spec + 5, *colon = strrchr(a, ':');
        int tries;
        s_player = 1;
        if (!colon) {
            snprintf(err, errn, "The address needs a port, like 203.0.113.5:47001.");
            return -1;
        }
        snprintf(host, sizeof host, "%.*s", (int)(colon - a), a);
        snprintf(port, sizeof port, "%s", colon + 1);
        if (getaddrinfo(host, port, &hints, &res) != 0) {
            snprintf(err, errn, "Couldn't find %s. Check the address.", host);
            return -1;
        }
        for (tries = 0; tries < 120; tries++) {     /* two minutes for the host to start */
            u_long nb = 1;
            fd_set f;
            struct timeval tv = {1, 0};
            snprintf(msg, sizeof msg, "Joining %s on port %s...%s", host, port,
                     tries ? "\n\nNo answer yet: is the host waiting, and is the port open?" : "");
            netplay_status(msg);
            check_cancel();
            s_sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
            ioctlsocket(s_sock, FIONBIO, &nb);
            connect(s_sock, res->ai_addr, (int)res->ai_addrlen);
            FD_ZERO(&f);
            FD_SET(s_sock, &f);
            if (select(0, NULL, &f, NULL, &tv) > 0) {
                int e = 0, el = sizeof e;
                getsockopt(s_sock, SOL_SOCKET, SO_ERROR, (char *)&e, &el);
                if (!e) {
                    nb = 0;
                    ioctlsocket(s_sock, FIONBIO, &nb);
                    break;
                }
            }
            closesocket(s_sock);
            s_sock = INVALID_SOCKET;
            Sleep(500);
        }
        freeaddrinfo(res);
    } else {
        snprintf(err, errn, "RECOMP_NETPLAY must be host:<port> or join:<address>:<port>.");
        return -1;
    }
    if (s_sock == INVALID_SOCKET) {
        snprintf(err, errn, "Couldn't connect to the host. Check the address, and that the host's port is open.");
        return -1;
    }
    setsockopt(s_sock, IPPROTO_TCP, TCP_NODELAY, (const char *)&one, sizeof one);
    {
        uint32_t v = PROTOCOL, n;
        void *r;
        netplay_send_blob(&v, 4);
        r = netplay_recv_blob(&n);
        if (!r || n != 4 || memcmp(r, &v, 4)) {
            free(r);
            snprintf(err, errn, "The other player has a different Speed Force version.");
            return -1;
        }
        free(r);
    }
    netplay_status("Connected. Checking the connection...");
    measure_rtt();
    say("connected: player %d, round trip %u ms", s_player + 1, s_rtt_ms);
    return 0;
}

/* ---------------------------------------------------------------- the per-poll exchange */

static void compare_hash(int slot)
{
    /* both sides' hashes for the same poll are in: compare once */
    if (s_my_hash_at[slot] != s_their_hash_at[slot] || s_my_hash_at[slot] == 0)
        return;
    s_checks++;
    if (s_my_hash[slot] != s_their_hash[slot]) {
        s_desyncs++;
        if (s_desyncs <= 5)
            say("DESYNC at poll %u: this side %016llx, other side %016llx", s_my_hash_at[slot],
                (unsigned long long)s_my_hash[slot], (unsigned long long)s_their_hash[slot]);
        if (s_desyncs == 1)
            nv2a_overlay_toast("Online: out of sync with the other player. Restart the online game.");
    } else if (s_checks <= 3 || s_checks % 50 == 0) {
        say("in sync at poll %u (%d checks, %d desynced)", s_my_hash_at[slot], s_checks, s_desyncs);
    }
    if (s_log) {
        fprintf(s_log, "%u %016llx %016llx %s\n", s_my_hash_at[slot],
                (unsigned long long)s_my_hash[slot], (unsigned long long)s_their_hash[slot],
                s_my_hash[slot] == s_their_hash[slot] ? "ok" : "DESYNC");
        fflush(s_log);
    }
    s_my_hash_at[slot] = s_their_hash_at[slot] = 0;
}

static DWORD WINAPI recv_thread(LPVOID unused)
{
    Msg m;
    (void)unused;
    while (recv_all(&m, sizeof m) == 0 && m.type != MSG_BYE) {
        EnterCriticalSection(&s_lock);
        if (m.type == MSG_INPUT) {
            memcpy(s_remote[m.frame % RING], m.data, 20);
            if ((int64_t)m.frame > s_remote_upto)
                s_remote_upto = m.frame;
            WakeAllConditionVariable(&s_cv);
        } else if (m.type == MSG_HASH && s_hash_every) {
            int slot = (int)((m.frame / (uint32_t)s_hash_every) % (RING / 64));
            memcpy(&s_their_hash[slot], m.data, 8);
            s_their_hash_at[slot] = m.frame;
            compare_hash(slot);
        }
        LeaveCriticalSection(&s_lock);
    }
    EnterCriticalSection(&s_lock);
    InterlockedExchange(&s_remote_gone, 1);
    WakeAllConditionVariable(&s_cv);
    LeaveCriticalSection(&s_lock);
    say("the other player left (%d checks, %d desynced)", s_checks, s_desyncs);
    return 0;
}

static void on_exit_bye(void)
{
    Msg m;
    if (s_sock == INVALID_SOCKET)
        return;
    memset(&m, 0, sizeof m);
    m.type = MSG_BYE;
    send_all(&m, sizeof m);
    shutdown(s_sock, SD_SEND);
    upnp_close();
}

void netplay_start(int delay, int hash_every)
{
    const char *e;
    s_delay = delay > 0 && delay < RING / 2 ? delay : 8;
    s_hash_every = hash_every >= 0 ? hash_every : 300;
    if ((e = getenv("RECOMP_NETPLAY_LOG")) && *e)
        s_log = fopen(e, "w");
    timeBeginPeriod(1);
    atexit(on_exit_bye);
    CloseHandle(CreateThread(NULL, 0, recv_thread, NULL, 0, NULL));
    s_started = 1;
    say("started: you are player %d, input delay %d polls (%d ms), RAM check every %d polls",
        s_player + 1, s_delay, s_delay * 1000 / 60, s_hash_every);
}

int netplay_on(void)
{
    return s_started;
}

int netplay_player(void)
{
    return s_player;
}

static void send_hash(uint32_t frame)
{
    Msg m;
    uint64_t h = xbox_GuestStateHashBytes((const void *)(uintptr_t)g_xbox_mem_offset,
                                          g_xbox_total_ram ? g_xbox_total_ram : (64u << 20));
    int slot = (int)((frame / (uint32_t)s_hash_every) % (RING / 64));
    memset(&m, 0, sizeof m);
    m.type = MSG_HASH;
    m.frame = frame;
    memcpy(m.data, &h, 8);
    send_all(&m, sizeof m);
    EnterCriticalSection(&s_lock);
    s_my_hash[slot] = h;
    s_my_hash_at[slot] = frame;
    compare_hash(slot);
    LeaveCriticalSection(&s_lock);
}

/* 60 polls a second of real time. The deterministic clock moves when the
 * guest is idle, not with the wall clock, so without this the game would
 * run as fast as the PC allows. After a pause (a load, a wait for the other
 * player) the schedule starts again from now instead of catching up. */
static void pace(void)
{
    static uint64_t next;
    const uint64_t period = 1000000 / 60;
    uint64_t now = now_us();
    if (!next || now > next + 100000) {
        next = now + period;
        return;
    }
    if (now + 2000 < next)
        Sleep((DWORD)((next - now - 1500) / 1000));
    while (now_us() < next)
        YieldProcessor();
    next += period;
}

void netplay_frame(const uint8_t local[20], uint8_t ports[2][20])
{
    uint32_t k = s_frame++;
    Msg m;
    static const uint8_t idle[20] = {0, 20};

    /* the RAM as it is before this poll's input: the same point on both sides */
    if (s_hash_every && k && k % (uint32_t)s_hash_every == 0 && !s_remote_gone)
        send_hash(k);

    /* this side's controller now, for poll k + delay */
    memcpy(s_local[(k + s_delay) % RING], local, 20);
    if (!s_remote_gone) {
        memset(&m, 0, sizeof m);
        m.type = MSG_INPUT;
        m.frame = k + (uint32_t)s_delay;
        memcpy(m.data, local, 20);
        send_all(&m, sizeof m);
    }

    if (k < (uint32_t)s_delay) {
        memcpy(ports[0], idle, 20);
        memcpy(ports[1], idle, 20);
        pace();
        return;
    }
    EnterCriticalSection(&s_lock);
    if (s_remote_upto < (int64_t)k && !s_remote_gone) {
        uint64_t a = now_us(), told = a;
        while (s_remote_upto < (int64_t)k && !s_remote_gone) {
            SleepConditionVariableCS(&s_cv, &s_lock, 250);
            if (now_us() - told > 2000000) {
                told = now_us();
                say("waiting for the other player (poll %u)...", k);
                nv2a_overlay_toast("Online: waiting for the other player...");
            }
        }
        s_wait_us += now_us() - a;
        s_waits++;
    }
    {
        const uint8_t *mine = s_local[k % RING];
        const uint8_t *theirs = s_remote_upto >= (int64_t)k ? s_remote[k % RING] : idle;
        memcpy(ports[s_player], mine, 20);
        memcpy(ports[1 - s_player], theirs, 20);
    }
    LeaveCriticalSection(&s_lock);
    if (s_remote_gone && !InterlockedExchange(&s_told_gone, 1))
        nv2a_overlay_toast("Online: player %d left the game. You can keep playing.", 2 - s_player);
    if (k % 3600 == 0 && k)
        say("poll %u: waited %llu times, %.1f ms on average", k, (unsigned long long)s_waits,
            s_waits ? (double)s_wait_us / 1000.0 / (double)s_waits : 0.0);
    pace();
}
