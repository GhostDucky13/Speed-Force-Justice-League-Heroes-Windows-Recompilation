@echo off
rem Builds jlh_upscale.dll (MSVC, static runtime) into payload_src\upscale with the vendors'
rem runtime DLLs. Needs the SDKs unpacked in payload_src\sdk:
rem   DLSS\        https://github.com/NVIDIA/DLSS
rem   FidelityFX\  https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK (Kits\FidelityFX)
rem   xess\        https://github.com/intel/xess (release package: inc, lib, bin)
setlocal
set "R=%~dp0.."
set "SRC=%R%\jlh-upscale"
set "SDK=%R%\payload_src\sdk"
set "OUT=%R%\payload_src\upscale"
for /f "usebackq delims=" %%I in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VS=%%I"
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
if not exist "%OUT%" mkdir "%OUT%"
if not exist "%SRC%\obj" mkdir "%SRC%\obj"
pushd "%SRC%\obj"
cl /nologo /O2 /MT /EHsc /W3 /LD /I"%SDK%\DLSS\include" /I"%SDK%\FidelityFX\Kits\FidelityFX\api\include" /I"%SDK%\FidelityFX\Kits\FidelityFX\upscalers\include" /I"%SDK%\xess\inc" "%SRC%\jlh_upscale.cpp" /Fe:jlh_upscale.dll ^
   /link "%SDK%\DLSS\lib\Windows_x86_64\x64\nvsdk_ngx_s.lib" "%SDK%\FidelityFX\Kits\FidelityFX\signedbin\amd_fidelityfx_loader_dx12.lib" "%SDK%\xess\lib\libxess.lib" d3d12.lib d3d11.lib dxgi.lib advapi32.lib user32.lib || (popd & echo UPSCALE BUILD FAILED & exit /b 2)
copy /y jlh_upscale.dll "%OUT%\" >nul
copy /y "%SDK%\DLSS\lib\Windows_x86_64\rel\nvngx_dlss.dll" "%OUT%\" >nul
copy /y "%SDK%\FidelityFX\Kits\FidelityFX\signedbin\amd_fidelityfx_loader_dx12.dll" "%OUT%\" >nul
copy /y "%SDK%\FidelityFX\Kits\FidelityFX\signedbin\amd_fidelityfx_upscaler_dx12.dll" "%OUT%\" >nul
copy /y "%SDK%\xess\bin\libxess.dll" "%OUT%\" >nul
popd
echo UPSCALE BUILD OK
