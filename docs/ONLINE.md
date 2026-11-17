# Playing online

Speed Force 3.0.1 lets two players on two different computers play *Justice League Heroes*
together over the internet or a home network. Windows and Linux (including Steam Deck) can play
with each other in any combination.

> Online play is in the **3.0.1 pre-release** ([Releases](../../../releases)). It works in our
> tests but hasn't been tried by many players yet; please
> [report](#reporting-a-problem) how it goes, good or bad.

- [How it works](#how-it-works)
- [Before you start](#before-you-start)
- [Quick start](#quick-start)
- [Choosing how to connect](#choosing-how-to-connect)
- [Windows and Windows](#windows-and-windows)
- [Linux and Linux (and Steam Deck)](#linux-and-linux-and-steam-deck)
- [Linux and Windows](#linux-and-windows)
- [Port forwarding, step by step](#port-forwarding-step-by-step)
- [Tailscale and ZeroTier, step by step](#tailscale-and-zerotier-step-by-step)
- [During the game](#during-the-game)
- [Troubleshooting](#troubleshooting)
- [Advanced](#advanced)

## How it works

*Justice League Heroes* only has two players on one couch. Online play keeps it that way: **both
computers run the whole game**, and the only thing sent between them is each player's controller
input. Every frame, each game gets both players' buttons and runs exactly the same frame, so the
two copies stay identical. The game itself never knows it is online.

- One player **hosts** and is **player 1**. The other **joins** and is **player 2**.
- The connection is direct between the two computers, with no server in between. The host's
  computer has to be reachable from the joiner's: on the same home network, through a forwarded
  port, or through a free virtual network such as Tailscale or ZeroTier (see
  [Choosing how to connect](#choosing-how-to-connect)).
- Each player's input is held back a few frames (the **input delay**) so it has time to reach the
  other computer. The delay is chosen from the ping when you connect: about 0.07 s (4 frames) on
  a home network or a nearby friend, about 0.1 s for a ping around 100 ms, more for distant players. You get used to it quickly in a brawler like this one.
- To keep the two games identical, online play runs the game in a strict, step-by-step mode. It
  needs more CPU than normal play, so a slower computer may not keep 60 fps (see
  [Troubleshooting](#troubleshooting)).
- About every 5 seconds the two games compare their state. If they ever differ, both players
  are told, and you start the session again.

## Before you start

Both players need:

1. **The same Speed Force version** (3.0.1 or newer, the same on both computers). The launcher's
   About page shows the version and offers updates.
2. **The game built from the USA Xbox and PSP discs**, which the builder requires anyway. When you
   connect, the game checks that the files match on both sides. If someone added their own mods
   or changed game files, the game says "Your game files differ"; build it again (Windows: run
   the setup; Linux: About > Rebuild in the launcher).
3. **A controller** (or the keyboard). On each computer, that computer's first controller plays
   that computer's character. A second controller on the same computer is not used online.

What else to know:

- **The host's saves are used.** Before the game starts, the host sends its save files to the
  joiner. The joiner's own saves are not touched: the joiner plays on a temporary copy, which is
  cleared next time. **Progress made online is saved on the host's computer only.**
- The game language is the host's.
- Graphics settings (resolution, frame generation, upscaling) are each player's own and don't
  have to match.
- A computer that already runs Speed Force at 60 fps with room to spare is best for hosting, but
  either side can host. What matters most is that the **host can be reached**.

## Quick start

**Host (player 1):**

1. Open the **Speed Force** launcher and go to the **Online** page.
2. Leave the port at **47001** (or choose another between 1024 and 65535) and press **Host game**.
3. A small window appears: "Hosting on port 47001. Waiting for player 2 to join..." It shows the
   address player 2 should type:
   - **over the internet**: your internet (public) address and the port, like `203.0.113.5:47001`.
     If Speed Force couldn't ask your router for it, the window says "your internet address"
     instead; see [Finding your addresses](#finding-your-addresses).
   - **on the same network**: your computer's local address, like `192.168.1.20:47001`.
   - The last line tells you whether your router opened the port automatically.
4. On Windows, the first time you host, Windows Firewall asks whether to allow Speed Force on the
   network. Click **Allow** (see [Windows Firewall](#windows-firewall)).
5. Send the address to your friend and wait. **Cancel** in the window stops hosting.

**Joiner (player 2):**

1. Open the launcher's **Online** page.
2. Type the host's address into **Host's address**, like `203.0.113.5:47001`. If you leave out
   `:47001`, port 47001 is used.
3. Press **Join game**. The game keeps trying for two minutes, so it doesn't matter who starts
   first.

When the two connect, both games check the files, the host sends its saves and the delay, and
the game starts on both computers. From the title screen, **player 1 starts a two-player game**
the usual way: pick Two Players in a new game or in Chapter Select, or load a save and add
player 2 from the pause menu.

The launcher remembers the port and the last address you joined.

## Choosing how to connect

| Situation | What to do |
|---|---|
| Both computers on the **same home network** | Join with the host's **local address** (`192.168.x.x:47001`). Nothing else needed. |
| Over the internet, and the host's router **opened the port automatically** (the host window says so) | Join with the host's **internet address**. Nothing else needed. |
| Over the internet, the router **didn't open the port** | Either [forward the port](#port-forwarding-step-by-step) on the host's router, or use [Tailscale or ZeroTier](#tailscale-and-zerotier-step-by-step). |
| The host can't change router settings (shared housing, dorm, mobile internet, "CGNAT") | Use [Tailscale or ZeroTier](#tailscale-and-zerotier-step-by-step), or let the other player host. |

**If you're unsure, use Tailscale.** It is free for personal use, takes a few minutes to set up,
works on Windows, Linux and Steam Deck, and needs no router settings. Only the host has to be
reachable, so if one player's network is easy to open and the other's isn't, the easy one hosts.

### Finding your addresses

- **Local address** (same network): the host window shows it. You can also find it on Windows
  under Settings > Network & internet > (your connection) > Properties, "IPv4 address", or on
  Linux with `ip -4 addr` (the one starting with 192.168., 10. or 172.16-31.).
- **Internet address**: the host window shows it when the router answered. Otherwise, open a
  site such as [whatismyip.com](https://www.whatismyip.com) on the host's computer, or look on the
  router's status page ("WAN IP").
- **Behind CGNAT?** If the router's status page shows a WAN address different from the one
  websites show you, or one starting with `100.64.` to `100.127.`, your internet provider shares
  one address between many customers, and port forwarding can't work. Use Tailscale or ZeroTier,
  or let the other player host.
- Online play uses IPv4 addresses. Tailscale and ZeroTier addresses are IPv4 too.

## Windows and Windows

This is the simplest case.

1. **Host:** Online > **Host game**. When Windows Firewall asks, allow Speed Force (tick
   **Private networks**; tick Public too if your home network is set to Public).
2. Look at the last line of the host window:
   - "**Your router opened the port automatically.**": send the **internet address** line to your
     friend.
   - "If player 2 can't connect: forward this TCP port...": your router doesn't do automatic port
     opening (UPnP), or has it turned off. Either turn on UPnP in the router's settings, [forward
     the port by hand](#port-forwarding-step-by-step), or use [Tailscale](#tailscale-and-zerotier-step-by-step).
3. **Joiner:** Online > type the address > **Join game**.

On the same network, use the local address instead; the router isn't involved.

### Windows Firewall

The first time a Speed Force host waits for a player, Windows asks "Do you want to allow
SpeedForce.exe on this network?" Allow it. If you clicked Cancel by mistake, the joiner can't
connect. To fix it:

1. Open **Windows Security > Firewall & network protection > Allow an app through firewall**.
2. Click **Change settings**, find **SpeedForce.exe** (or Justice League Heroes) and tick
   **Private** (and **Public** if needed). If it isn't listed, use **Allow another app...** and
   pick `SpeedForce.exe` in your Speed Force folder (by default
   `%LOCALAPPDATA%\Programs\Speed Force`).

The joiner doesn't need any firewall change.

Other security software (Norton, Bitdefender, and so on) can have its own firewall. Allow
`SpeedForce.exe` there too.

## Linux and Linux (and Steam Deck)

The Linux launcher (the AppImage) has the same **Online** page. The game runs through Proton or
Wine, and online play works the same way through either.

1. **Host:** Online > **Host game**. The host window shows the addresses.
2. Most desktop Linux systems don't block incoming connections by default, but some do:
   - **Ubuntu / Mint with ufw turned on:** `sudo ufw allow 47001/tcp`
   - **Fedora / openSUSE (firewalld):** `sudo firewall-cmd --add-port=47001/tcp` (add
     `--permanent` and run `sudo firewall-cmd --reload` to keep it after a restart)
   - **Steam Deck / SteamOS:** no firewall by default.
3. **Over the internet:** the game asks the router to open the port through Wine as well. If the
   host window doesn't say "Your router opened the port automatically", [forward the
   port](#port-forwarding-step-by-step) or use [Tailscale or ZeroTier](#tailscale-and-zerotier-step-by-step).
4. **Joiner:** Online > type the address > **Join game**.

**Steam Deck:**

- The launcher runs in **Desktop Mode**. Start online play from there. To type the address, open
  the on-screen keyboard with **Steam + X**.
- If you added the AppImage to Steam to start it from Game Mode, the Online page works there
  too: use Steam + X for the keyboard.
- The first controller is the Deck's own controls. Online, that is your character.
- Tailscale can be installed on SteamOS, but it takes some extra steps because the system is
  read-only. The community [deck-tailscale](https://github.com/tailscale-dev/deck-tailscale) script
  does it. The Steam Deck can also simply be the joiner, which needs nothing installed.

## Linux and Windows

A Windows computer and a Linux computer (or Steam Deck) can play together. Either one can host.
Speed Force 3.0.1 computes the game's math the same way on every system and every processor
(Intel or AMD), so the two stay in step.

- **Windows hosts:** follow the host steps in [Windows and Windows](#windows-and-windows). The
  Linux player joins from the Online page.
- **Linux hosts:** follow the host steps in [Linux and Linux](#linux-and-linux-and-steam-deck).
  The Windows player joins from the Online page and needs no firewall change.
- Both need the same Speed Force version, built from the USA discs (the Windows setup and the
  Linux AppImage of the same version build the same game).
- Tailscale and ZeroTier work across systems: the Windows player installs the Windows app, the
  Linux player the Linux one, both sign in to the same network, and the joiner uses the host's
  Tailscale or ZeroTier address.

## Port forwarding, step by step

Only the **host** forwards a port, and only once.

**The easy way first:** many routers have a **UPnP** setting (sometimes "UPnP IGD" or "NAT-PMP").
Turn it on, and the game opens the port by itself each time you host and closes it when the game
ends; the host window then says "Your router opened the port automatically." If your router has
no UPnP, or you'd rather not turn it on, forward the port by hand:

1. **Give the host computer a fixed local address**, so the forward doesn't break when it
   changes. In the router's settings this is usually called "DHCP reservation", "static lease"
   or "address reservation": pick the host computer and reserve its current address (the
   local address in the host window).
2. **Open the router's settings page.** It is usually at `192.168.1.1` or `192.168.0.1` (it's
   often printed on the router, along with the login).
3. Find **Port forwarding** (also "Virtual server", "NAT", "Applications" or "Gaming").
4. Add a rule:
   - **Protocol:** TCP
   - **External port:** 47001 (or the port you host on)
   - **Internal port:** the same
   - **Internal IP / device:** the host computer's local address
5. Save.
6. Host again and give your friend your **internet address** with the port.

If it still doesn't work, check the host computer's firewall (above) and whether you are behind
CGNAT ([Finding your addresses](#finding-your-addresses)).

## Tailscale and ZeroTier, step by step

Tailscale and ZeroTier put both computers on a private virtual network over the internet, as if
they were in the same house. No router settings are needed, and they work behind CGNAT.

**Tailscale** ([tailscale.com](https://tailscale.com), free for personal use):

1. Both players install Tailscale: [Windows](https://tailscale.com/download/windows),
   [Linux](https://tailscale.com/download/linux) (one command, `curl -fsSL
   https://tailscale.com/install.sh | sh`, then `sudo tailscale up`), Steam Deck (see
   [above](#linux-and-linux-and-steam-deck)).
2. The host signs in and **shares their computer** with the friend (in the Tailscale admin page,
   on the host machine: **Share...**), or invites the friend to their tailnet. The friend
   accepts with their own account.
3. The host's Tailscale address is shown in the Tailscale app (it starts with `100.`, like
   `100.101.102.103`).
4. **Host:** Online > Host game. **Joiner:** Online > join `100.101.102.103:47001` (the host's
   Tailscale address).

**ZeroTier** ([zerotier.com](https://www.zerotier.com), free for small networks):

1. One player creates a network at [my.zerotier.com](https://my.zerotier.com) and copies its
   network ID.
2. Both install ZeroTier and **join** that network ID. The creator ticks **Auth** for both
   computers on the network's page.
3. The host's ZeroTier address is listed there ("Managed IPs").
4. **Host:** Online > Host game. **Joiner:** join `<host ZeroTier address>:47001`.

With a virtual network, the host's firewall still has to allow the game (Windows asks the first
time; on Linux see the firewall commands above).

## During the game

- **Pausing:** either player can pause. Because it's the same game on both computers, it pauses
  for both.
- **Menus:** both controllers work in the menus, as on a couch. Player 1 usually drives them.
- **If one computer is slower**, both games wait for it, so the game runs at the speed of the
  slower one. A message "Online: waiting for the other player..." appears when the other side
  hasn't answered for a moment.
- **If a player leaves** (closes the game or loses the connection), the other sees "player 2 left
  the game. You can keep playing." (or player 1) and carries on alone. A session can't be
  rejoined: to play together again, both close the game and connect again.
- **"Out of sync":** the two games stopped being identical. This shouldn't happen, but if it
  does, close both games and start a new session from the last save. Please report it (see
  [Reporting a problem](#reporting-a-problem)).
- **Saving:** the game saves as usual; on the host's computer that is the host's real save. The
  joiner's copy is temporary.

## Troubleshooting

| What you see | What to do |
|---|---|
| Joiner: "Joining ... No answer yet: is the host waiting, and is the port open?" for two minutes, then "Couldn't connect to the host" | The host must be on the waiting window first (or within two minutes). Check the address and port. Over the internet, the host's port must be open (router said so, or [forwarded](#port-forwarding-step-by-step)) and the host's firewall must allow the game. Try the same network or Tailscale to narrow it down. |
| Joiner: "Couldn't find ... Check the address." | The address is mistyped. Use numbers like `203.0.113.5:47001` (or a name your computer can look up, such as a Tailscale MagicDNS name). |
| Host: "Port 47001 is already in use on this PC" | Another program (or another copy of the game) uses that port. Close it, or host on another port and give that port to the joiner. |
| "The other player has a different Speed Force version." | Both update to the same version (launcher > About). |
| "Your game files differ from the other player's." | One side has mods or changed files, or was built from other discs. Build the game again (Windows: run the setup; Linux: About > Rebuild). |
| The game runs slowly or stutters online but not offline | Online play needs more CPU. Lower **resolution scale** and turn off **frame generation** in the launcher's settings (or F10 in game), close other programs, and plug laptops in. The slower computer sets the speed for both. |
| The input feels late | The delay comes from the ping. Playing over a home network or with a closer friend lowers it. Wi-Fi adds jitter: a cable helps. |
| "Online: out of sync with the other player. Restart the online game." | Start a new session. Please report it with both players' game logs. |
| Windows: the joiner can't connect even on the same network | Windows Firewall blocked the game on the host. See [Windows Firewall](#windows-firewall). Also check the network is set to **Private** on the host. |
| Linux: the joiner can't connect even on the same network | The host's firewall blocks the port: see the ufw / firewalld commands in [Linux and Linux](#linux-and-linux-and-steam-deck). |

### Reporting a problem

Open an issue on GitHub with what happened, both players' systems (Windows / Linux / Steam Deck),
and both game logs: Windows `SpeedForce.log` in the Speed Force folder (launcher > About > Open
game log), Linux `SpeedForce-linux.log` in the install folder. Online lines start with
`[NETPLAY]`.

## Advanced

The launcher only sets one environment variable before starting the game. You can start
`SpeedForce.exe` yourself with it (for example from a script or a Steam launch option):

| Variable | Meaning |
|---|---|
| `RECOMP_NETPLAY=host:47001` | Host on port 47001 (all network adapters). |
| `RECOMP_NETPLAY=host:192.168.1.20:47001` | Host on one address only. |
| `RECOMP_NETPLAY=join:203.0.113.5:47001` | Join that host. |
| `RECOMP_NETPLAY_DELAY=6` | Host only: use this input delay in frames (4 to 30) instead of the one chosen from the ping. |
| `RECOMP_NETPLAY_LOG=<file>` | Write each state check (frame, both sides' values, ok / DESYNC) to a file. |

On Linux, set them in the environment of the Proton or Wine command that runs `SpeedForce.exe`
(the launcher does this for you).

Technical details: the two games run deterministically (a virtual clock instead of the real one,
and the game's threads in a fixed order), the controller reports for frame *k* are sent at frame
*k − delay* over TCP, and the state check is a hash of the game's 64 MB of memory every 300
frames. The code is in `toolkit/src/usb/netplay.c` and `game/src/main.c` (`jlh_netplay_setup`).
