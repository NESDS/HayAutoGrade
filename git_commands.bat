@echo off
git add .
git commit -m "Fix DB migration and update Excel data - update_conflicts.py now recreates table completely, updated hag.xlsx with additional fixes"
git push origin main
echo Done!
pause