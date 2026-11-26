$ErrorActionPreference='Stop'
$base=Split-Path $PSScriptRoot -Parent
if ([IO.Path]::GetPathRoot($base) -ne 'E:\') { throw 'Keep Meridian Desk on E:.' }
$env:TEMP=Join-Path $base 'cache\temp'
$env:TMP=$env:TEMP
$sdk=Join-Path $PSScriptRoot 'webview2'
foreach ($dll in 'Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll') {
    Copy-Item -LiteralPath (Join-Path $sdk "lib\net462\$dll") -Destination (Join-Path $base $dll) -Force
}
Copy-Item -LiteralPath (Join-Path $sdk 'runtimes\win-x64\native\WebView2Loader.dll') -Destination $base -Force
$csc=Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc /nologo /optimize+ /target:winexe /platform:x64 "/win32icon:$base\app\meridian.ico" "/out:$base\Meridian Desk.exe" "/r:$base\Microsoft.Web.WebView2.Core.dll" "/r:$base\Microsoft.Web.WebView2.WinForms.dll" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$PSScriptRoot\Meridian.cs"
if ($LASTEXITCODE -ne 0) { throw 'Native build failed.' }
