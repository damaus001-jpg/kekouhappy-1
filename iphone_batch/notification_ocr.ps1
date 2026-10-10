param([Parameter(Mandatory=$true)][string]$ImagePath)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$taskAsyncMethod=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await-OcrTask($Operation,$ResultType) {
    $taskAsync=$taskAsyncMethod.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
    if (!$taskAsync.Wait(15000)) { throw 'OCR operation timed out' }
    return $taskAsync.Result
}
$taskFile=Await-OcrTask ([Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$taskStream=Await-OcrTask ($taskFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime])
try {
    $taskDecoder=Await-OcrTask ([Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]::CreateAsync($taskStream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $taskBitmap=Await-OcrTask ($taskDecoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,[Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
        $taskEngine=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]::TryCreateFromUserProfileLanguages()
        if (!$taskEngine) { throw 'No local OCR language available' }
        $taskResult=Await-OcrTask ($taskEngine.RecognizeAsync($taskBitmap)) ([Windows.Media.Ocr.OcrResult])
        $taskLines=@($taskResult.Lines | ForEach-Object {
            $taskWords=@($_.Words | ForEach-Object { [pscustomobject]@{text=$_.Text;x=$_.BoundingRect.X;y=$_.BoundingRect.Y;w=$_.BoundingRect.Width;h=$_.BoundingRect.Height} })
            [pscustomobject]@{text=$_.Text;words=$taskWords}
        })
        [pscustomobject]@{lines=$taskLines} | ConvertTo-Json -Depth 5 -Compress
    } finally { if ($taskBitmap) { $taskBitmap.Dispose() } }
} finally { $taskStream.Dispose() }
