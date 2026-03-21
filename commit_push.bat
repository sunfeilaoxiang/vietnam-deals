@echo off
cd /d "C:\Users\dsdar\Documents\vietnam-deals"

echo ==========================================
echo  Committing syntax fixes and pushing
echo ==========================================
echo.

del /q _decode.py 2>nul
del /q setup_git.bat 2>nul
del /q push_fix.bat 2>nul
del /q push_now.bat 2>nul

git add -A
git commit -m "Fix syntax errors from chunk-boundary line merges in scorer, scraper, site_generator"
git push --force origin main

echo.
echo ==========================================
echo  DONE - Press any key to close
echo ==========================================
pause >nul