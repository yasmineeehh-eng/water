$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

Write-Host "Installing dependencies..."
py -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

Write-Host "Building WaterRPA.exe..."
py -m PyInstaller --clean --noconfirm waterRPA_GUI.spec

Write-Host ""
Write-Host "Build complete: $PSScriptRoot\dist\WaterRPA.exe"
