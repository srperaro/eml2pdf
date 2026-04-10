@echo off
setlocal EnableDelayedExpansion
title EML to PDF — Build

echo.
echo ============================================================
echo   EML to PDF Converter  —  Build Script
echo ============================================================
echo.

:: ── Check Python ────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.9+ from https://python.org
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   Python : %%v

:: ── Install / upgrade dependencies ──────────────────────────────────────────
echo.
echo [1/3] Installing dependencies...
pip install --quiet --upgrade ^
    reportlab ^
    pypdf ^
    pillow ^
    beautifulsoup4 ^
    pyinstaller

if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause & exit /b 1
)
echo   OK.

:: ── Clean previous build ────────────────────────────────────────────────────
if exist dist\eml2pdf.exe (
    echo.
    echo   Removing previous build...
    del /q dist\eml2pdf.exe
)

:: ── Build ────────────────────────────────────────────────────────────────────
echo.
echo [2/3] Building executable (this may take a minute)...
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "eml2pdf" ^
    --collect-all reportlab ^
    --collect-all PIL ^
    --hidden-import bs4 ^
    --hidden-import pypdf ^
    --hidden-import email ^
    gui.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check the output above for details.
    pause & exit /b 1
)

:: ── Result ───────────────────────────────────────────────────────────────────
echo.
echo [3/3] Build complete!
echo.
echo   Executable : dist\eml2pdf.exe
echo.
echo   You can distribute dist\eml2pdf.exe standalone.
echo   No Python or pip needed on the target machine.
echo.
pause
