@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /WX /LD connect_local.cpp /Fe:LocalEOSConnect.dll
if errorlevel 1 exit /b 1
copy /Y LocalEOSConnect.dll EOSSDK-Win64-Shipping.dll >nul
exit /b %errorlevel%
