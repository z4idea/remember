@echo off
chcp 65001 >nul
echo 正在打包为 exe，请确保已安装: pip install -r requirements.txt
pyinstaller remember.spec
echo.
echo 完成后 exe 位于: dist\日程提醒.exe
pause
