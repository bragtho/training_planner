@echo off
rem Baut das Programm nach dist\Wissens-Manager (Single Directory)
cd /d "%~dp0"
.venv\Scripts\pyinstaller --noconfirm wissens_manager.spec
