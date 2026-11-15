@echo off
rem Builds the Speed Force programs with LLVM-MinGW (clang + windres on PATH, or LLVM=<bin dir>):
rem   SpeedForceLauncher.exe  the launcher            SpeedForceBuilder.exe  the setup (without its build kit)
rem   sfpack.exe              packs the build kit that is appended to the builder (see setup\make_setup.bat)
setlocal
cd /d "%~dp0"
if defined LLVM set "PATH=%LLVM%;%PATH%"
windres sflauncher.rc -O coff -o sflauncher.res || exit /b 1
clang -O2 -municode -mwindows sflauncher.c sflauncher.res -lgdiplus -ldwmapi -lole32 -luuid -lshell32 -lwinhttp -o SpeedForceLauncher.exe || exit /b 2
windres sfbuilder.rc -O coff -o sfbuilder.res || exit /b 3
clang -O2 -municode -mwindows sfbuilder.c sfbuilder.res -lgdiplus -ldwmapi -lcabinet -lole32 -luuid -lshell32 -lcomdlg32 -lshlwapi -luxtheme -o SpeedForceBuilder.exe || exit /b 4
clang -O2 -municode sfpack.c -lcabinet -o sfpack.exe || exit /b 5
del sflauncher.res sfbuilder.res
echo LAUNCHER BUILD OK
