param(
    [Parameter(Mandatory = $true)][string]$MeteorSource,
    [Parameter(Mandatory = $true)][string]$WindSource,
    [Parameter(Mandatory = $true)][string]$LightningSource,
    [string]$OutputDirectory = "public/game/tex/effects"
)

Add-Type -AssemblyName System.Drawing

$outputPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null

function Write-EffectStrip {
    param([string]$Source, [string]$Name)

    $sourceImage = [System.Drawing.Bitmap]::FromFile($Source)
    try {
        $output = New-Object System.Drawing.Bitmap 1280, 128, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($output)
            try {
                $graphics.Clear([System.Drawing.Color]::Transparent)
                $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceOver
                $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $cellWidth = $sourceImage.Width / 10.0
                for ($index = 0; $index -lt 10; $index++) {
                    $sourceRect = New-Object System.Drawing.RectangleF ($index * $cellWidth), 0, $cellWidth, $sourceImage.Height
                    $targetRect = New-Object System.Drawing.RectangleF ($index * 128 + 5), 5, 118, 118
                    $graphics.DrawImage($sourceImage, $targetRect, $sourceRect, [System.Drawing.GraphicsUnit]::Pixel)
                }
            }
            finally {
                $graphics.Dispose()
            }
            $destination = Join-Path $outputPath "$Name.png"
            $output.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
            Write-Output $destination
        }
        finally {
            $output.Dispose()
        }
    }
    finally {
        $sourceImage.Dispose()
    }
}

Write-EffectStrip -Source $MeteorSource -Name "meteor"
Write-EffectStrip -Source $WindSource -Name "wind"
Write-EffectStrip -Source $LightningSource -Name "lightning"
