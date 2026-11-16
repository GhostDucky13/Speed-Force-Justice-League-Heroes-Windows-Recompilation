#!/usr/bin/env python3
"""
make_appdir.py - assembles the Speed Force AppDir (then appimagetool makes the AppImage).

  python3 linux/make_appdir.py --kit <downloads> --deps <payload_src> --out <AppDir>

<downloads> holds what docs/BUILDING.md lists for Linux: python-build-standalone (with Tk),
the numpy / Pillow / capstone wheels (wheels/), llvm-mingw (ubuntu), CMake, Ninja, a portable
Wine (Kron4ek wow64 build), DXVK and vkd3d-proton. <payload_src> is the Windows setup's
(SDL3, dsp56300.tar.gz, librashader.zip, upscale/). No game files are involved.

  AppDir/AppRun                          starts usr/python with the Speed Force app
  AppDir/usr/python                      Python 3.13 + Tk + numpy, Pillow, capstone
  AppDir/usr/share/speedforce/app        speedforce_linux.py and its images
  AppDir/usr/share/speedforce/kit        the build kit, copied to <install>/_build to build
  AppDir/usr/share/speedforce/tools      llvm/ (LLVM-MinGW), cmake/, ninja/
  AppDir/usr/share/speedforce/wine       a portable Wine, used only when there's no Proton or Wine
  AppDir/usr/share/speedforce/dxvk       DXVK + vkd3d-proton (Direct3D 11 / 12 on Vulkan)
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # repository root


def one(kit, pattern):
    m = sorted(glob.glob(os.path.join(kit, pattern)))
    if not m:
        sys.exit(f'missing in {kit}: {pattern}')
    return m[-1]


def untar_flat(archive, dst):
    """Extract an archive whose content sits in one top folder, without that folder."""
    tmp = dst + '.tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    if archive.endswith('.zst'):
        subprocess.check_call(['tar', '--zstd', '-xf', archive, '-C', tmp])
    else:
        with tarfile.open(archive) as t:
            t.extractall(tmp, filter='tar')
    tops = os.listdir(tmp)
    src = os.path.join(tmp, tops[0]) if len(tops) == 1 and os.path.isdir(os.path.join(tmp, tops[0])) else tmp
    shutil.rmtree(dst, ignore_errors=True)
    shutil.move(src, dst)
    shutil.rmtree(tmp, ignore_errors=True)


def kit(out, deps):
    """The build kit: what <install>/_build holds while building (as the Windows setup's)."""
    ign = shutil.ignore_patterns('__pycache__', '*.pyc')
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for d in ('toolkit', 'game', 'jlh-upscale'):
        shutil.copytree(os.path.join(R, d), os.path.join(out, d), ignore=ign)
    s = os.path.join(out, 'setup')
    os.makedirs(s)
    for f in ('sf_extract.py', 'sf_buildmod.py', 'sf_install.py', 'sf_saves.py'):
        shutil.copy2(os.path.join(R, 'setup', f), s)
    shutil.copytree(os.path.join(R, 'setup', 'modtools'), os.path.join(s, 'modtools'), ignore=ign)
    d = os.path.join(out, 'deps')
    os.makedirs(d)
    shutil.copytree(os.path.join(deps, 'SDL3'), os.path.join(d, 'SDL3'))
    shutil.copy2(os.path.join(deps, 'dsp56300.tar.gz'), d)
    shutil.copy2(os.path.join(deps, 'librashader.zip'), d)
    rt = os.path.join(out, 'runtime')
    os.makedirs(rt)
    for f in ('jlh_upscale.dll', 'nvngx_dlss.dll', 'amd_fidelityfx_loader_dx12.dll',
              'amd_fidelityfx_upscaler_dx12.dll', 'libxess.dll'):
        shutil.copy2(os.path.join(deps, 'upscale', f), rt)
    shutil.copy2(os.path.join(R, 'assets', 'jlh_icons.pack'), rt)
    for f in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'LEGAL.txt', 'README.md', 'FEATURES.md'):
        shutil.copy2(os.path.join(R, f), rt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kit', required=True)
    ap.add_argument('--deps', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--kit-only', help='only write the build kit to this folder (for tests)')
    a = ap.parse_args()
    if a.kit_only:
        kit(a.kit_only, a.deps)
        return
    A = os.path.abspath(a.out)
    shutil.rmtree(A, ignore_errors=True)
    share = os.path.join(A, 'usr', 'share', 'speedforce')
    os.makedirs(share)
    # Python with Tk, plus the build's Python packages
    untar_flat(one(a.kit, 'cpython-3.13*-x86_64-unknown-linux-gnu-install_only*.tar.gz'), os.path.join(A, 'usr', 'python'))
    py = os.path.join(A, 'usr', 'python', 'bin', 'python3')
    subprocess.check_call([py, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile', '-q']
                          + sorted(glob.glob(os.path.join(a.kit, 'wheels', '*.whl'))))
    for t in ('idlelib', 'turtledemo', 'test', 'ensurepip', 'pydoc_data'):
        for p in glob.glob(os.path.join(A, 'usr', 'python', 'lib', 'python3.*', t)):
            shutil.rmtree(p, ignore_errors=True)
    # compilers
    tools = os.path.join(share, 'tools')
    untar_flat(one(a.kit, 'llvm-mingw-*-ucrt-ubuntu-*-x86_64.tar.xz'), os.path.join(tools, 'llvm'))
    for arch in ('aarch64', 'armv7', 'i686', 'arm64ec'):      # only x86_64 Windows is built
        for p in glob.glob(os.path.join(tools, 'llvm', arch + '-w64-mingw32*')):
            shutil.rmtree(p, ignore_errors=True)
    for n in ('clangd', 'clang-tidy', 'lldb', 'lldb-server', 'lldb-mi', 'lldb-dap', 'lldb-argdumper'):
        for p in glob.glob(os.path.join(tools, 'llvm', 'bin', n)):
            os.remove(p)
    untar_flat(one(a.kit, 'cmake-*-linux-x86_64.tar.gz'), os.path.join(tools, 'cmake'))
    shutil.rmtree(os.path.join(tools, 'cmake', 'doc'), ignore_errors=True)
    shutil.rmtree(os.path.join(tools, 'cmake', 'man'), ignore_errors=True)
    os.makedirs(os.path.join(tools, 'ninja'))
    zipfile.ZipFile(one(a.kit, 'ninja-linux.zip')).extractall(os.path.join(tools, 'ninja'))
    os.chmod(os.path.join(tools, 'ninja', 'ninja'), 0o755)
    # the build kit
    kit(os.path.join(share, 'kit'), a.deps)
    # Wine (fallback) and the graphics layers
    untar_flat(one(a.kit, 'wine-*-amd64-wow64.tar.xz'), os.path.join(share, 'wine'))
    shutil.rmtree(os.path.join(share, 'wine', 'include'), ignore_errors=True)
    untar_flat(one(a.kit, 'dxvk-*.tar.gz'), os.path.join(share, 'dxvk.tmp'))
    untar_flat(one(a.kit, 'vkd3d-proton-*.tar.*'), os.path.join(share, 'vkd3d.tmp'))
    dx = os.path.join(share, 'dxvk')
    os.makedirs(dx)
    for p in glob.glob(os.path.join(share, 'dxvk.tmp', 'x64', '*.dll')) + \
            glob.glob(os.path.join(share, 'vkd3d.tmp', 'x64', '*.dll')):
        shutil.copy2(p, dx)
    shutil.rmtree(os.path.join(share, 'dxvk.tmp'))
    shutil.rmtree(os.path.join(share, 'vkd3d.tmp'))
    # the app
    app = os.path.join(share, 'app')
    os.makedirs(app)
    shutil.copy2(os.path.join(R, 'linux', 'speedforce_linux.py'), app)
    for f in ('icon.png', 'banner.png'):
        shutil.copy2(os.path.join(R, 'launcher', f), app)
    shutil.copytree(os.path.join(R, 'linux', 'fonts'), os.path.join(app, 'fonts'))
    shutil.copy2(os.path.join(R, 'launcher', 'icon.png'), os.path.join(A, 'speedforce.png'))
    shutil.copy2(os.path.join(R, 'launcher', 'icon.png'), os.path.join(A, '.DirIcon'))
    shutil.copy2(os.path.join(R, 'linux', 'speedforce.desktop'), A)
    shutil.copy2(os.path.join(R, 'linux', 'AppRun'), A)
    os.chmod(os.path.join(A, 'AppRun'), 0o755)
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(A) for f in fs
                if not os.path.islink(os.path.join(dp, f)))
    print(f'AppDir ready: {total / 1e6:.0f} MB in {A}')


if __name__ == '__main__':
    main()
