#!/usr/bin/env python3
"""Builds payload/ - what the Speed Force setup copies to <install dir>\\_build - from the
repository and payload_src/ (the downloaded build tools and third-party files, see
docs/BUILDING.md). No game files are involved."""
import os, shutil, sys, tarfile, zipfile

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # repository root
G = os.path.dirname(R)
SRC = os.path.join(R, 'payload_src')
P = os.path.join(R, 'payload')


def unzip_flat(z, dst):
    """Extract a zip whose content sits in one top folder, without that folder."""
    with zipfile.ZipFile(z) as f:
        names = f.namelist()
        top = os.path.commonprefix(names).split('/')[0] + '/' if '/' in names[0] else ''
        for n in names:
            if n.endswith('/'):
                continue
            rel = n[len(top):] if top and n.startswith(top) else n
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with f.open(n) as s, open(out, 'wb') as o:
                shutil.copyfileobj(s, o)


def main():
    shutil.rmtree(P, ignore_errors=True)
    os.makedirs(P)
    # Python (embeddable) + numpy, Pillow, capstone
    py = os.path.join(P, 'python')
    unzip_flat(os.path.join(SRC, 'python-embed.zip'), py)
    shutil.copytree(os.path.join(SRC, 'pysite'), os.path.join(py, 'Lib', 'site-packages'))
    for n in os.listdir(py):
        if n.endswith('._pth'):
            zipname = n.replace('._pth', '.zip')
            open(os.path.join(py, n), 'w').write(f'{zipname}\n.\nLib\\site-packages\n')
    # compilers
    unzip_flat(os.path.join(SRC, 'llvm-mingw.zip'), os.path.join(P, 'llvm'))
    unzip_flat(os.path.join(SRC, 'cmake.zip'), os.path.join(P, 'cmake'))
    unzip_flat(os.path.join(SRC, 'ninja.zip'), os.path.join(P, 'ninja'))
    # sources
    ign = shutil.ignore_patterns('__pycache__', '*.pyc')
    shutil.copytree(os.path.join(R, 'toolkit'), os.path.join(P, 'toolkit'), ignore=ign)
    shutil.copytree(os.path.join(R, 'game'), os.path.join(P, 'game'), ignore=ign)
    shutil.copytree(os.path.join(R, 'jlh-upscale'), os.path.join(P, 'jlh-upscale'), ignore=ign)
    s = os.path.join(P, 'setup')
    os.makedirs(s)
    for f in ('sf_extract.py', 'sf_buildmod.py', 'sf_install.py', 'sf_saves.py'):
        shutil.copy2(os.path.join(R, 'setup', f), s)
    shutil.copytree(os.path.join(R, 'setup', 'modtools'), os.path.join(s, 'modtools'), ignore=ign)
    # third-party build inputs
    d = os.path.join(P, 'deps')
    os.makedirs(d)
    shutil.copytree(os.path.join(SRC, 'SDL3'), os.path.join(d, 'SDL3'))
    shutil.copy2(os.path.join(SRC, 'dsp56300.tar.gz'), os.path.join(d, 'dsp56300.tar.gz'))
    shutil.copy2(os.path.join(SRC, 'librashader.zip'), os.path.join(d, 'librashader.zip'))
    # runtime files beside the game: the upscaler bridge and the vendors' runtimes, button icons
    rt = os.path.join(P, 'runtime')
    os.makedirs(rt)
    bm = os.path.join(SRC, 'upscale')          # jlh_upscale.dll built by setup/build_upscale.bat + vendor runtimes
    for f in ('jlh_upscale.dll', 'nvngx_dlss.dll', 'amd_fidelityfx_loader_dx12.dll',
              'amd_fidelityfx_upscaler_dx12.dll', 'libxess.dll'):
        shutil.copy2(os.path.join(bm, f), rt)
    shutil.copy2(os.path.join(R, 'assets', 'jlh_icons.pack'), rt)
    for f in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'LEGAL.txt', 'README.md', 'FEATURES.md'):
        if os.path.exists(os.path.join(R, f)):
            shutil.copy2(os.path.join(R, f), rt)
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(P) for f in fs)
    print(f'payload ready: {total / 1e6:.0f} MB')


if __name__ == '__main__':
    main()
