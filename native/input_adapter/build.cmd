@echo off
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 exit /b 1
cd /d "%~dp0"
if not exist build mkdir build
python write_manifest.py --prepare
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /EHsc /O2 /MD /LD adapter.cpp /Fobuild\adapter.obj /Febuild\ashes_input_adapter.dll /link user32.lib advapi32.lib /IMPLIB:build\ashes_input_adapter.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /EHsc /O2 /MD fixture.cpp /Fobuild\fixture.obj /Febuild\ashes_input_fixture.exe /link user32.lib
if errorlevel 1 exit /b 1
python write_manifest.py
exit /b %errorlevel%
