# Making your own dumps

Speed Force needs disc images of **your own** copies of Justice League Heroes for the original
Xbox and for the PSP (both USA releases). Downloading these images from the internet is not
legal in most countries; dump the discs you own.

## Xbox
Use a modded Xbox with an FTP-capable dashboard, or a compatible DVD drive with a dumping tool
that produces a Redump-style image. Either a full image or an XISO (game partition only) works:
the setup finds the game partition. The checksum the setup expects is that of the image you
dumped (see README).

## PSP
Use a PSP with custom firmware: the UMD can be saved as an ISO from the firmware's recovery or
VSH menu (USB "UMD disc" mode), then copied to the PC.

## Checking a dump
In PowerShell: `Get-FileHash "<image>" -Algorithm SHA1`, then compare with the table in the README.
