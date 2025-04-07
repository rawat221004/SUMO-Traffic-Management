@echo off
REM =================================================================
REM HOW TO RUN THIS FILE:
REM - In PowerShell: Use .\run.bat
REM - In Command Prompt: Use run.bat
REM =================================================================

setlocal enabledelayedexpansion

REM Check if required files exist
set MISSING_FILES=0
for %%F in (osm.net.xml.gz osm.passenger.trips.xml emergency_routes.xml osm.poly.xml.gz vehicle_types.add.xml traffic_signals.add.xml osm.sumocfg osm.view.xml) do (
    if not exist %%F (
        echo ERROR: Required file %%F is missing.
        set /a MISSING_FILES+=1
    )
)

if !MISSING_FILES! neq 0 (
    echo !MISSING_FILES! required file(s) are missing. Please check the files listed above.
    goto :error
)

echo Starting SUMO simulation...
REM Use the correct GUI settings file (osm.view.xml as specified in the config)
sumo-gui -c osm.sumocfg --start --delay 100

if %ERRORLEVEL% neq 0 (
    echo.
    echo An error occurred while running SUMO. Error code: %ERRORLEVEL%
    goto :error
)

goto :end

:error
echo.
echo Press any key to exit...
pause >nul

:end