# Format the generated document through Word's native object model.
param([Parameter(Mandatory=$true)][string]$Path, [string]$InspectionPdf)
$ErrorActionPreference = 'Stop'
function Rgb([int]$r,[int]$g,[int]$b) { return $r + 256*$g + 65536*$b }
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $document = $word.Documents.Open($Path,$false,$false)
    $document.PageSetup.PageWidth = 595.28
    $document.PageSetup.PageHeight = 841.89
    $document.PageSetup.TopMargin = 62.36
    $document.PageSetup.BottomMargin = 59.53
    $document.PageSetup.LeftMargin = 62.36
    $document.PageSetup.RightMargin = 62.36
    $document.PageSetup.FooterDistance = 25
    $document.Content.Font.Name = 'Arial'
    $document.Content.Font.Size = 10.5
    $document.Content.Font.Color = (Rgb 23 39 53)
    $document.Content.ParagraphFormat.SpaceAfter = 6
    $document.Content.ParagraphFormat.LineSpacingRule = 5
    $document.Content.ParagraphFormat.LineSpacing = 15
    $document.Content.ParagraphFormat.WidowControl = -1
    foreach ($id in @(-2,-3,-4)) {
        $style = $document.Styles.Item($id)
        $style.Font.Name = 'Arial'
        $style.Font.Color = (Rgb 22 62 85)
        $style.Font.Size = $(if ($id -eq -2) { 16 } else { 12 })
        $style.ParagraphFormat.SpaceBefore = 12
        $style.ParagraphFormat.SpaceAfter = 7
        $style.ParagraphFormat.KeepWithNext = -1
    }
    $inCover = $true
    foreach ($paragraph in $document.Paragraphs) {
        $text = $paragraph.Range.Text.Trim([char]13,[char]7)
        if ($text.Contains('[[PAGEBREAK]]')) {
            $inCover = $false
            continue
        }
        if ($inCover) {
            $paragraph.Alignment = 1
            $paragraph.SpaceAfter = 10
            $paragraph.Range.Font.Color = (Rgb 22 62 85)
            if ($text -like 'INFORME T*') {
                $paragraph.SpaceBefore = 55
                $paragraph.SpaceAfter = 35
                $paragraph.Range.Font.Size = 10
            } elseif ($text -eq 'Gemelo digital de movilidad urbana en Cali') {
                $paragraph.Range.Font.Size = 25
                $paragraph.Range.Font.Bold = -1
                $paragraph.SpaceAfter = 22
            } elseif ($text -like 'Dise*o y evaluaci*n*') {
                $paragraph.Range.Font.Size = 14
                $paragraph.SpaceAfter = 55
            } elseif ($text.Contains('Quintero Estrada')) {
                $paragraph.Range.Font.Size = 12
                $paragraph.Range.Font.Bold = -1
            } elseif ($text.Contains('Cali, Colombia')) {
                $paragraph.SpaceBefore = 75
                $paragraph.Range.Font.Size = 11
            }
        } elseif ($paragraph.OutlineLevel -ge 1 -and $paragraph.OutlineLevel -le 3) {
            $paragraph.Alignment = 0
            $paragraph.Range.Font.Size = $(if ($paragraph.OutlineLevel -eq 1) { 16 } else { 12 })
            $paragraph.Range.Font.Bold = -1
            $paragraph.Range.Font.Color = (Rgb 22 62 85)
            $paragraph.SpaceBefore = 12
            $paragraph.SpaceAfter = 7
            $paragraph.KeepWithNext = -1
            if ($paragraph.OutlineLevel -eq 1 -and $text -match '^(1\.|2\.|6\.|10\.|Anexo\.)') {
                $paragraph.PageBreakBefore = -1
            }
        } elseif ($paragraph.Range.Tables.Count -eq 0) {
            $paragraph.Alignment = 3
            if ($text -match '^(Tabla |Figura )') {
                $paragraph.Range.Font.Size = 9
                $paragraph.Alignment = 0
                if ($text.StartsWith('Tabla ')) { $paragraph.KeepWithNext = -1 }
            }
            if ($text -match '^\[\d+\]') {
                $paragraph.Range.Font.Size = 9
                $paragraph.Alignment = 0
            }
        }
    }
    $marker = $document.Content.Duplicate
    $marker.Find.ClearFormatting()
    $marker.Find.Text = '[[PAGEBREAK]]'
    if ($marker.Find.Execute()) { $marker.Text = ''; $marker.InsertBreak(7) }
    foreach ($table in $document.Tables) {
        $table.AutoFitBehavior(2)
        $table.Range.Font.Size = 9
        $table.Range.ParagraphFormat.SpaceBefore = 1
        $table.Range.ParagraphFormat.SpaceAfter = 3
        $table.Range.ParagraphFormat.Alignment = 0
        $table.Rows.AllowBreakAcrossPages = 0
        $table.Rows.Item(1).HeadingFormat = -1
        for ($i=1; $i -le $table.Rows.Count; $i++) {
            $row = $table.Rows.Item($i)
            if ($i -eq 1) {
                $row.Shading.BackgroundPatternColor = (Rgb 22 62 85)
                $row.Range.Font.Color = (Rgb 255 255 255)
                $row.Range.Font.Bold = -1
            } else {
                $row.Range.Font.Color = (Rgb 23 39 53)
                $row.Shading.BackgroundPatternColor = $(if ($i % 2 -eq 0) { Rgb 243 246 247 } else { Rgb 255 255 255 })
            }
        }
    }
    $footer = $document.Sections.Item(1).Footers.Item(1).Range
    $footer.Text = 'Gemelo digital de Cali  |  '
    $footer.Font.Name = 'Arial'
    $footer.Font.Size = 8
    $footer.ParagraphFormat.Alignment = 1
    $end = $footer.Duplicate
    $end.SetRange($footer.End-1,$footer.End-1)
    $document.Fields.Add($end,33) | Out-Null
    $document.Repaginate()
    $document.Fields.Update() | Out-Null
    $document.Save()
    if ($InspectionPdf) { $document.ExportAsFixedFormat($InspectionPdf,17) }
    Write-Output "Word document verified; pages: $($document.ComputeStatistics(2))"
} catch {
    Write-Output $_.ScriptStackTrace
    throw
} finally {
    if ($document) { $document.Close(0); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) | Out-Null }
    if ($word) { $word.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null }
}
