# ============================================
# Aries AI - Build Verification Script
# ============================================
# This script verifies that all build artifacts exist

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Aries AI - Build Verification      " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# Check 1: Backend agent.exe
Write-Host "[1/6] Checking backend agent.exe..." -ForegroundColor Yellow
$backendExe = ".\backend\agent.exe"
if (Test-Path $backendExe) {
    $size = (Get-Item $backendExe).Length / 1MB
    Write-Host "  ✓ Found: $backendExe" -ForegroundColor Green
    Write-Host "    Size: $([math]::Round($size, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Missing: $backendExe" -ForegroundColor Red
    Write-Host "    Action: Build Python backend first" -ForegroundColor Yellow
    $allGood = $false
}
Write-Host ""

# Check 2: Frontend dist folder
Write-Host "[2/6] Checking frontend dist folder..." -ForegroundColor Yellow
if (Test-Path ".\dist\index.html") {
    $fileCount = (Get-ChildItem -Path ".\dist" -Recurse -File).Count
    Write-Host "  ✓ Found: .\dist\index.html" -ForegroundColor Green
    Write-Host "    Files: $fileCount total files in dist" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Missing: .\dist\index.html" -ForegroundColor Red
    Write-Host "    Action: Run 'npm run build'" -ForegroundColor Yellow
    $allGood = $false
}
Write-Host ""

# Check 3: Electron executable
Write-Host "[3/6] Checking Electron executable..." -ForegroundColor Yellow
$exePath = ".\release\win-unpacked\Aries AI.exe"
if (Test-Path $exePath) {
    $size = (Get-Item $exePath).Length / 1MB
    Write-Host "  ✓ Found: $exePath" -ForegroundColor Green
    Write-Host "    Size: $([math]::Round($size, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Missing: $exePath" -ForegroundColor Red
    Write-Host "    Action: Run 'npm run package'" -ForegroundColor Yellow
    $allGood = $false
}
Write-Host ""

# Check 4: Installer
Write-Host "[4/6] Checking installer..." -ForegroundColor Yellow
$installer = Get-ChildItem ".\release\*.exe" -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*Setup*" } | Select-Object -First 1
if ($installer) {
    $size = $installer.Length / 1MB
    Write-Host "  ✓ Found: $($installer.Name)" -ForegroundColor Green
    Write-Host "    Size: $([math]::Round($size, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Missing: Installer (.exe)" -ForegroundColor Red
    Write-Host "    Action: Run 'npm run package'" -ForegroundColor Yellow
    $allGood = $false
}
Write-Host ""

# Check 5: Bundled backend in release
Write-Host "[5/6] Checking bundled backend..." -ForegroundColor Yellow
$bundledBackend = ".\release\win-unpacked\resources\backend\agent.exe"
if (Test-Path $bundledBackend) {
    $size = (Get-Item $bundledBackend).Length / 1MB
    Write-Host "  ✓ Found: $bundledBackend" -ForegroundColor Green
    Write-Host "    Size: $([math]::Round($size, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Missing: $bundledBackend" -ForegroundColor Red
    Write-Host "    Action: Backend not bundled in release" -ForegroundColor Yellow
    $allGood = $false
}
Write-Host ""

# Check 6: Build resources
Write-Host "[6/6] Checking build resources..." -ForegroundColor Yellow
$icon = ".\build\icon.ico"
if (Test-Path $icon) {
    Write-Host "  ✓ Found: $icon" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Missing: $icon (optional)" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "  ✓ All Checks Passed!                " -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Your build is complete and ready to use!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Run the app:" -ForegroundColor Yellow
    Write-Host "  .\release\win-unpacked\Aries AI.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "Or install:" -ForegroundColor Yellow
    if ($installer) {
        Write-Host "  .\release\$($installer.Name)" -ForegroundColor White
    }
} else {
    Write-Host "  ✗ Some Checks Failed                " -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Please fix the issues above and try again." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Quick fix:" -ForegroundColor Yellow
    Write-Host "  npm run package" -ForegroundColor White
}
Write-Host ""
