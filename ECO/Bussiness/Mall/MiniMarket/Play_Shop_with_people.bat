@echo off
rem Double-click to play.  WASD walk, SHIFT hurry, E action, TAB swap boy, ESC quit.
setlocal
set PLAYER=E:\UPBGE\upbge-0.50-windows-x64\blenderplayer.exe
set GAME=%~dp0Shop_with_people.blend
if not exist "%PLAYER%" (
  echo Could not find %PLAYER%
  echo Edit this file and point PLAYER at your UPBGE blenderplayer.exe
  pause
  exit /b 1
)
"%PLAYER%" -g noaudio "%GAME%"
pause
