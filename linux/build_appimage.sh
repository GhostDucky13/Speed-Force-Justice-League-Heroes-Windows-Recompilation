#!/bin/sh
# build_appimage.sh <AppDir> <out dir> - packs the AppDir (from make_appdir.py) into the AppImage,
# with update information, so AppImageUpdate can update it from the GitHub releases. Writes
# SpeedForce-<version>-x86_64.AppImage and its .zsync; attach both to the release.
# Needs appimagetool (APPIMAGETOOL=<path>, default: appimagetool on the PATH). RUNTIME=<file> uses
# a downloaded type2 runtime instead of fetching one. UPDATE_TAG=latest-pre makes a pre-release
# AppImage update only from pre-releases (default: latest, the newest stable release).
set -e
APPDIR=$(cd "${1:?AppDir}" && pwd)
OUT=${2:?out dir}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
TOOL=${APPIMAGETOOL:-appimagetool}
VERSION=$(sed -n 's/^X-AppImage-Version=//p' "$APPDIR/speedforce.desktop")
UPDATE="gh-releases-zsync|GhostDucky13|Speed-Force-Justice-League-Heroes-Windows-Recompilation|${UPDATE_TAG:-latest}|SpeedForce-*-x86_64.AppImage.zsync"
mkdir -p "$OUT"
cd "$OUT"
set -- --comp zstd -u "$UPDATE"
[ -n "$RUNTIME" ] && set -- "$@" --runtime-file "$RUNTIME"
ARCH=x86_64 VERSION=$VERSION "$TOOL" "$@" "$APPDIR" "SpeedForce-$VERSION-x86_64.AppImage"
ls -l "SpeedForce-$VERSION-x86_64.AppImage" "SpeedForce-$VERSION-x86_64.AppImage.zsync"
