/*
 * sfpack.c - packs a folder into a Speed Force payload archive (.sfar), compressed with the
 * Windows Compression API (LZMS), for SpeedForceBuilder.exe to carry and unpack.
 *
 *   sfpack <out.sfar> <source>=<archive path> ...    (a source is a folder or a file)
 *   copy /b SpeedForceBuilder.exe + out.sfar SpeedForce-Setup.exe
 *
 * Archive:  "SFAR" u32 version(1) u32 files u64 raw_total
 *           files x { u16 path_len, path (UTF-8, '/' separated), u64 size }
 *           blocks  { u32 raw_len, u32 comp_len, comp_len bytes }  (file data, back to back)
 *           trailer u64 archive_size, "SFPAYLD2"
 * Build: clang -O2 -municode sfpack.c -lcabinet -o sfpack.exe
 */
#ifndef UNICODE
#define UNICODE
#endif
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0A00
#include <windows.h>
#include <compressapi.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <wchar.h>

#define BLOCK (32u << 20)

typedef struct { wchar_t *full; char *rel; uint64_t size; } Ent;
static Ent *g_ents;
static int g_n, g_cap;

static const wchar_t *g_prefix;

static void add(const wchar_t *full, const wchar_t *rel, uint64_t size)
{
    Ent *e;
    wchar_t r2[MAX_PATH * 2];
    int n, i;
    if (g_n == g_cap) {
        g_cap = g_cap ? g_cap * 2 : 1024;
        g_ents = (Ent *)realloc(g_ents, sizeof(Ent) * (size_t)g_cap);
    }
    e = &g_ents[g_n++];
    e->full = _wcsdup(full);
    swprintf(r2, MAX_PATH * 2, L"%ls%ls%ls", g_prefix, (g_prefix[0] && rel[0]) ? L"/" : L"", rel);
    n = WideCharToMultiByte(CP_UTF8, 0, r2, -1, NULL, 0, NULL, NULL);
    e->rel = (char *)malloc((size_t)n);
    WideCharToMultiByte(CP_UTF8, 0, r2, -1, e->rel, n, NULL, NULL);
    for (i = 0; e->rel[i]; i++)
        if (e->rel[i] == '\\')
            e->rel[i] = '/';
    e->size = size;
}

static void walk(const wchar_t *root, const wchar_t *sub)
{
    wchar_t pat[MAX_PATH * 2];
    WIN32_FIND_DATAW fd;
    HANDLE h;
    swprintf(pat, MAX_PATH * 2, L"%ls%ls%ls\\*", root, sub[0] ? L"\\" : L"", sub);
    h = FindFirstFileW(pat, &fd);
    if (h == INVALID_HANDLE_VALUE)
        return;
    do {
        wchar_t rel[MAX_PATH * 2];
        if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L".."))
            continue;
        swprintf(rel, MAX_PATH * 2, L"%ls%ls%ls", sub, sub[0] ? L"\\" : L"", fd.cFileName);
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            walk(root, rel);
        } else {
            wchar_t full[MAX_PATH * 2];
            swprintf(full, MAX_PATH * 2, L"%ls\\%ls", root, rel);
            add(full, rel, ((uint64_t)fd.nFileSizeHigh << 32) | fd.nFileSizeLow);
        }
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

/* Reads the next block of file data (the files back to back). */
static int g_cur = 0;
static FILE *g_f = NULL;

static uint32_t fill_block(unsigned char *buf)
{
    uint32_t fill = 0;
    while (fill < BLOCK) {
        size_t got;
        if (!g_f) {
            if (g_cur >= g_n) break;
            g_f = _wfopen(g_ents[g_cur].full, L"rb");
            if (!g_f) {
                fwprintf(stderr, L"cannot read %ls\n", g_ents[g_cur].full);
                exit(1);
            }
            g_cur++;
        }
        got = fread(buf + fill, 1, BLOCK - fill, g_f);
        fill += (uint32_t)got;
        if (got == 0) {
            fclose(g_f);
            g_f = NULL;
        }
    }
    return fill;
}

typedef struct { unsigned char *raw, *comp; uint32_t rl; SIZE_T cl; HANDLE th; int ok; } Job;
#define CAP (BLOCK + BLOCK / 2 + (1u << 20))

static DWORD WINAPI compress_job(void *arg)
{
    Job *j = (Job *)arg;
    COMPRESSOR_HANDLE c;
    j->ok = 0;
    if (!CreateCompressor(COMPRESS_ALGORITHM_LZMS, NULL, &c))
        return 0;
    j->ok = Compress(c, j->raw, j->rl, j->comp, CAP, &j->cl) ? 1 : 0;
    CloseCompressor(c);
    return 0;
}

int wmain(int argc, wchar_t **argv)
{
    FILE *out;
    uint32_t ver = 1, files;
    uint64_t total = 0, written = 0, archive = 0;
    int i, nt;
    Job jobs[16];
    SYSTEM_INFO si;
    if (argc < 3) {
        fwprintf(stderr, L"usage: sfpack <out.sfar> <source>=<archive path> ...\n");
        return 2;
    }
    for (i = 2; i < argc; i++) {
        wchar_t *eq = wcsrchr(argv[i], L'=');
        WIN32_FILE_ATTRIBUTE_DATA a;
        if (!eq) {
            fwprintf(stderr, L"expected <source>=<archive path>: %ls\n", argv[i]);
            return 2;
        }
        *eq = 0;
        g_prefix = eq + 1;
        if (!GetFileAttributesExW(argv[i], GetFileExInfoStandard, &a)) {
            fwprintf(stderr, L"not found: %ls\n", argv[i]);
            return 2;
        }
        if (a.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            walk(argv[i], L"");
        } else {
            const wchar_t *p = g_prefix;
            g_prefix = L"";
            add(argv[i], p, ((uint64_t)a.nFileSizeHigh << 32) | a.nFileSizeLow);
            g_prefix = p;
        }
    }
    files = (uint32_t)g_n;
    for (i = 0; i < g_n; i++)
        total += g_ents[i].size;
    out = _wfopen(argv[1], L"wb");
    if (!out) {
        fwprintf(stderr, L"cannot write %ls\n", argv[1]);
        return 1;
    }
    fwrite("SFAR", 1, 4, out);
    fwrite(&ver, 4, 1, out);
    fwrite(&files, 4, 1, out);
    fwrite(&total, 8, 1, out);
    archive = 20;
    for (i = 0; i < g_n; i++) {
        uint16_t l = (uint16_t)strlen(g_ents[i].rel);
        fwrite(&l, 2, 1, out);
        fwrite(g_ents[i].rel, 1, l, out);
        fwrite(&g_ents[i].size, 8, 1, out);
        archive += 2 + l + 8;
    }
    /* blocks are compressed in parallel, one compressor per thread, and written in order */
    GetSystemInfo(&si);
    nt = (int)si.dwNumberOfProcessors;
    if (nt > 8) nt = 8;
    if (nt < 1) nt = 1;
    for (i = 0; i < nt; i++) {
        jobs[i].raw = (unsigned char *)malloc(BLOCK);
        jobs[i].comp = (unsigned char *)malloc(CAP);
    }
    for (;;) {
        int n = 0;
        for (i = 0; i < nt; i++) {
            jobs[i].rl = fill_block(jobs[i].raw);
            if (!jobs[i].rl) break;
            jobs[i].th = CreateThread(NULL, 0, compress_job, &jobs[i], 0, NULL);
            n++;
        }
        for (i = 0; i < n; i++) {
            uint32_t cl;
            WaitForSingleObject(jobs[i].th, INFINITE);
            CloseHandle(jobs[i].th);
            if (!jobs[i].ok) {
                fwprintf(stderr, L"compress failed\n");
                return 1;
            }
            cl = (uint32_t)jobs[i].cl;
            fwrite(&jobs[i].rl, 4, 1, out);
            fwrite(&cl, 4, 1, out);
            fwrite(jobs[i].comp, 1, jobs[i].cl, out);
            archive += 8 + jobs[i].cl;
            written += jobs[i].rl;
        }
        fwprintf(stdout, L"  %llu / %llu MB\r", written >> 20, total >> 20);
        fflush(stdout);
        if (n < nt) break;
    }
    archive += 16;
    fwrite(&archive, 8, 1, out);
    fwrite("SFPAYLD2", 1, 8, out);
    fclose(out);
    wprintf(L"\npacked %u files, %llu MB -> %llu MB with %d threads\n", files, total >> 20, archive >> 20, nt);
    return 0;
}
