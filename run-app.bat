@echo off
rem Flutter app on Chrome. Start run-backend.bat first. Needs flutter on PATH.
cd /d "%~dp0app"
flutter run -d chrome --web-port 5555
