@echo off
cd /d "C:\Users\dsdar\Documents\vietnam-deals"
echo === Cleaning up old files ===
del /q _decode.py 2>nul
del /q setup_git.bat 2>nul
del /q push_fix.bat 2>nul

echo === Git status ===
git status

echo === Adding all files ===
git add -A

echo === Committing ===
git commit -m "Update: stronger tag/category filtering, property detail cards, EUR currency"

echo === Pushing to GitHub ===
git push origin main

echo === Done! ===
pause