cd /d %~dp0
git pull
git add ./
git commit -m "autosave(Windows): %date:~0,10% %time:~0,-3%"
git push

timeout /t 3