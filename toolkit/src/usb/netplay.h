/*
 * netplay.h - delay-based online play for a title's own local multiplayer.
 *
 * Two copies of the game run on two PCs. Neither knows the other exists:
 * each sees two controllers on ports 1 and 2, exactly as on a couch. What
 * travels between them is only the controllers' reports, one per port-0
 * pad poll (the "frame" here, the same clock pad scripts call g<poll>):
 *
 *   - at poll k each side reads its own player's controller and sends that
 *     report, to be used at poll k + delay on both sides;
 *   - at poll k both sides feed the two reports meant for poll k to ports
 *     1 (the host's player) and 2 (the joiner's), waiting for the other
 *     side's report when it has not arrived yet, then wait for the real
 *     clock so the game runs at 60 polls a second.
 *
 * Both copies therefore see the same input at the same poll. That only
 * keeps them together if the game itself is deterministic: the game runs
 * with the virtual clock and the deterministic scheduler (RECOMP_DEBUG=
 * deterministic, RECOMP_GUEST_LOCK=1; the code generated with
 * --back-edge-yield), with the same files, saves and settings on both
 * sides, which the game checks and sends while it connects (the blobs).
 * Every hash_every polls each side hashes guest RAM and sends it; a
 * mismatch is shown as a desync.
 *
 * The sequence, from the game's start (before the kernel):
 *
 *   netplay_connect(spec)      shows a small window while it waits;
 *                              spec = host:[<address>:]<port> or
 *                              join:<address>:<port>
 *   netplay_send_blob / recv   the game's own handshake (versions, files,
 *                              saves, settings)
 *   netplay_start(delay, n)    from here netplay_on() is 1 and the pad
 *                              model calls netplay_frame each port-0 poll
 *
 *   RECOMP_NETPLAY_LOG=<path>  one line per RAM check, for comparing runs
 *
 * TCP, with Nagle off. On Windows the host asks the router to open its port
 * (UPnP) and shows the address a friend joins with.
 */
#ifndef XBOX_NETPLAY_H
#define XBOX_NETPLAY_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Connect as spec says, showing a window with the state and a Cancel
 * button (Cancel ends the process). 0 when connected; otherwise -1 with a
 * sentence for the player in err. */
int netplay_connect(const char *spec, char *err, size_t errn);

/* 1 on the host, 0 on the joiner (valid after netplay_connect). */
int netplay_is_host(void);

/* The round trip measured while connecting, in milliseconds. */
unsigned netplay_rtt_ms(void);

/* Handshake messages, before netplay_start: length-prefixed, whole. The
 * received buffer is malloc'd (free it); NULL when the link failed. */
int   netplay_send_blob(const void *p, uint32_t n);
void *netplay_recv_blob(uint32_t *n);

/* The waiting window's text (UTF-8), and closing it. */
void netplay_status(const char *utf8);
void netplay_close_window(void);

/* Begin the per-poll exchange. */
void netplay_start(int delay, int hash_every);

/* 1 once netplay_start ran. */
int netplay_on(void);

/* This side's player: 0 for the host (port 1), 1 for the joiner (port 2). */
int netplay_player(void);

/* Called with port 0's report as this side's controller makes it, at the
 * start of each port-0 poll. Sends it, waits for the reports meant for this
 * poll, paces to the real clock, and writes them: ports[0] for port 1,
 * ports[1] for port 2. */
void netplay_frame(const uint8_t local[20], uint8_t ports[2][20]);

/* A delay in polls for a round trip: enough for one way plus jitter. */
int netplay_delay_for_rtt(unsigned rtt_ms);

#ifdef __cplusplus
}
#endif

#endif /* XBOX_NETPLAY_H */
