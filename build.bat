@echo off
chcp 65001 >nul
rem 重新生成图标并打包成 dist\EPUB中文编辑器.exe
cd /d "%~dp0"
python build_icon.py || goto :error
python -m PyInstaller zhepub.spec --noconfirm --clean || goto :error
echo.
echo 打包完成：dist\EPUB中文编辑器.exe
pause
exit /b 0
:error
echo 打包失败，请先安装：pip install pyinstaller pillow
pause
exit /b 1
