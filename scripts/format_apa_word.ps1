# APA 7 body and the institutional cover supplied by the authors.
param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$CoverTemplate,
    [Parameter(Mandatory=$true)][string]$PdfPath
)
$ErrorActionPreference = 'Stop'
$word=$null; $document=$null; $reference=$null
try {
    $word=New-Object -ComObject Word.Application
    $word.Visible=$false; $word.DisplayAlerts=0; $word.AutomationSecurity=3
    $document=$word.Documents.Open($Path,$false,$false)
    $document.Content.Font.Name='Times New Roman'
    $document.Content.Font.Size=12
    $document.Content.Font.Color=0
    $document.Content.ParagraphFormat.Alignment=0
    $document.Content.ParagraphFormat.LineSpacingRule=2
    $document.Content.ParagraphFormat.SpaceBefore=0
    $document.Content.ParagraphFormat.SpaceAfter=0
    $document.Content.ParagraphFormat.FirstLineIndent=36
    $document.Content.ParagraphFormat.LeftIndent=0
    $document.Content.ParagraphFormat.RightIndent=0
    $document.Content.ParagraphFormat.WidowControl=-1
    foreach ($id in @(-1,-2,-3,-4)) {
        $style=$document.Styles.Item($id)
        $style.Font.Name='Times New Roman'; $style.Font.Size=12; $style.Font.Color=0
        $style.ParagraphFormat.SpaceBefore=0; $style.ParagraphFormat.SpaceAfter=0
        $style.ParagraphFormat.LineSpacingRule=2
        if ($id -ne -1) {
            $style.Font.Bold=-1; $style.ParagraphFormat.KeepWithNext=-1
            $style.ParagraphFormat.FirstLineIndent=0
        }
    }
    $reference=$word.Documents.Open($CoverTemplate,$false,$true)
    $secondPage=$reference.GoTo(1,1,2)
    $sourceCover=$reference.Range(0,$secondPage.Start-1)
    # The source page ends with a manual page break; the report supplies its own.
    while ($sourceCover.Text.Length -gt 0 -and [char]::IsWhiteSpace($sourceCover.Text[$sourceCover.Text.Length-1])) {
        $sourceCover.End=$sourceCover.End-1
    }
    if ($sourceCover.Text.Contains('El contenido de esta obra')) { throw 'Cover range includes the next page' }
    $destination=$document.Content.Duplicate
    $destination.Find.Text='[[INSTITUTIONAL_COVER]]'
    if (-not $destination.Find.Execute()) { throw 'Institutional cover marker not found' }
    $destination.FormattedText=$sourceCover.FormattedText
    $breakMarker=$document.Content.Duplicate
    $breakMarker.Find.Text='[[PAGEBREAK]]'
    if (-not $breakMarker.Find.Execute()) { throw 'Cover end marker not found' }
    $cover=$document.Range(0,$breakMarker.Start)
    foreach ($paragraph in $cover.Paragraphs) {
        $text=$paragraph.Range.Text
        if ($text.Contains('ENTORNOS IoT')) {
            $paragraph.Range.Text="GEMELO DIGITAL DE MOVILIDAD URBANA EN CALI`vCONTROL SEMAFÓRICO MULTIAGENTE MEDIANTE APRENDIZAJE POR REFUERZO`r"
            $paragraph.Range.Font.Bold=-1
            $paragraph.Alignment=1
        } elseif ($text.Trim([char]13,[char]7) -eq 'Milton Alberto Quintero Estrada') {
            $paragraph.Range.Text="Milton Alberto Quintero Estrada`vJose David Arias Pantoja`r"
            $paragraph.Alignment=1
        }
    }
    $breakMarker=$document.Content.Duplicate
    $breakMarker.Find.Text='[[PAGEBREAK]]'; $breakMarker.Find.Execute()|Out-Null
    $cover=$document.Range(0,$breakMarker.Start)
    $cover.Font.Name='Times New Roman'; $cover.Font.Size=12; $cover.Font.Color=0
    $cover.ParagraphFormat.Alignment=1
    $cover.ParagraphFormat.FirstLineIndent=0; $cover.ParagraphFormat.LeftIndent=0
    $cover.ParagraphFormat.SpaceBefore=0; $cover.ParagraphFormat.SpaceAfter=0
    $cover.ParagraphFormat.PageBreakBefore=0; $cover.ParagraphFormat.KeepWithNext=0
    $cover.ParagraphFormat.LineSpacingRule=2
    foreach($paragraph in $cover.Paragraphs) {
        if($paragraph.Range.Text.Trim().Length -eq 0){$paragraph.LineSpacingRule=0}
    }
    $afterCover=$false; $referenceSection=$false; $nextCaptionTitle=$false
    foreach ($paragraph in $document.Paragraphs) {
        $text=$paragraph.Range.Text.Trim([char]13,[char]7)
        if ($text.Contains('[[PAGEBREAK]]')) { $afterCover=$true; continue }
        if (-not $afterCover) { continue }
        $paragraph.SpaceBefore=0; $paragraph.SpaceAfter=0
        $paragraph.Range.Font.Name='Times New Roman'; $paragraph.Range.Font.Size=12
        $paragraph.Range.Font.Color=0; $paragraph.LineSpacingRule=2
        $paragraph.LeftIndent=0; $paragraph.RightIndent=0
        if ($paragraph.Range.Tables.Count -gt 0) { continue }
        if ($paragraph.OutlineLevel -ge 1 -and $paragraph.OutlineLevel -le 3) {
            $paragraph.FirstLineIndent=0
            $paragraph.Range.Font.Bold=-1
            $paragraph.Range.Font.Italic=$(if($paragraph.OutlineLevel -eq 3){-1}else{0})
            $paragraph.Alignment=$(if($paragraph.OutlineLevel -eq 1){1}else{0})
            $paragraph.KeepWithNext=-1
            $paragraph.PageBreakBefore=0
            if ($text -eq 'Referencias') { $referenceSection=$true; $paragraph.PageBreakBefore=-1 }
            if ($text -eq 'Apéndice A') { $referenceSection=$false; $paragraph.PageBreakBefore=-1 }
            if ($text -eq 'Gemelo digital de movilidad urbana en Cali') { $paragraph.PageBreakBefore=-1 }
            continue
        }
        $paragraph.Alignment=0
        if ($referenceSection) {
            $paragraph.LeftIndent=36; $paragraph.FirstLineIndent=-36
            $paragraph.KeepWithNext=0
        } elseif ($text -match '^(Tabla A?\d+|Figura \d+)$') {
            $paragraph.FirstLineIndent=0; $paragraph.Range.Font.Bold=-1
            $paragraph.KeepWithNext=-1; $nextCaptionTitle=$true
        } elseif ($nextCaptionTitle -and $text.Length -gt 0) {
            $paragraph.FirstLineIndent=0
            $paragraph.Range.Font.Italic=-1; $paragraph.Range.Font.Bold=0
            $paragraph.KeepWithNext=-1; $nextCaptionTitle=$false
        } elseif ($paragraph.Range.InlineShapes.Count -gt 0) {
            $paragraph.FirstLineIndent=0; $paragraph.Alignment=1
            $paragraph.LineSpacingRule=0; $paragraph.KeepWithNext=-1
        } elseif ($text.StartsWith('Nota.')) {
            $paragraph.FirstLineIndent=0; $paragraph.LineSpacingRule=0
        } elseif ($text.StartsWith('Se desarrolló un prototipo de gemelo digital')) {
            $paragraph.FirstLineIndent=0
        } elseif ($text.StartsWith('Media ±') -or $text.StartsWith('El P95 es')) {
            $paragraph.FirstLineIndent=0; $paragraph.LineSpacingRule=0
        } elseif ($text -match '^r.*=|^J\(x\)|^S\s*=') {
            $paragraph.FirstLineIndent=0; $paragraph.Alignment=1
        } elseif ($paragraph.Range.ListFormat.ListType -ne 0) {
            $paragraph.LeftIndent=36; $paragraph.FirstLineIndent=-18
        } else {
            $paragraph.FirstLineIndent=36
        }
    }
    $marker=$document.Content.Duplicate
    $marker.Find.Text='[[PAGEBREAK]]'
    if($marker.Find.Execute()) { $marker.Text=''; $marker.InsertBreak(7) }
    foreach ($table in $document.Tables) {
        $table.AutoFitBehavior(2)
        $table.Range.Font.Name='Times New Roman'; $table.Range.Font.Size=12
        $table.Range.Font.Color=0
        $table.Range.ParagraphFormat.FirstLineIndent=0
        $table.Range.ParagraphFormat.LeftIndent=0
        $table.Range.ParagraphFormat.Alignment=0
        $table.Range.ParagraphFormat.LineSpacingRule=0
        $table.Range.ParagraphFormat.SpaceBefore=0; $table.Range.ParagraphFormat.SpaceAfter=0
        $table.Shading.BackgroundPatternColor=16777215
        $table.Borders.Enable=0
        $table.Borders.Item(-1).LineStyle=1
        $table.Borders.Item(-3).LineStyle=1
        $table.Rows.Item(1).Borders.Item(-3).LineStyle=1
        $table.Rows.Item(1).Range.Font.Bold=-1
        $table.Rows.Item(1).Range.ParagraphFormat.Alignment=1
        $table.Rows.Item(1).HeadingFormat=-1
        $table.Rows.AllowBreakAcrossPages=0
    }
    foreach($shape in $document.InlineShapes) {
        $shape.LockAspectRatio=-1
        if($shape.Width -gt 468){$shape.Width=468}
        if($shape.Height -gt 420){$shape.Height=420}
    }
    foreach($section in $document.Sections) {
        $section.PageSetup.PageWidth=612; $section.PageSetup.PageHeight=792
        $section.PageSetup.TopMargin=72; $section.PageSetup.BottomMargin=72
        $section.PageSetup.LeftMargin=72; $section.PageSetup.RightMargin=72
        $section.PageSetup.HeaderDistance=36; $section.PageSetup.FooterDistance=36
        $section.PageSetup.DifferentFirstPageHeaderFooter=0
        foreach($footer in $section.Footers){if($footer.Exists){$footer.Range.Text=''}}
        $header=$section.Headers.Item(1).Range
        $header.Text=''
        $header.Font.Name='Times New Roman';$header.Font.Size=12
        $header.ParagraphFormat.Alignment=2
        $header.ParagraphFormat.FirstLineIndent=0
        $header.ParagraphFormat.SpaceBefore=0;$header.ParagraphFormat.SpaceAfter=0
        $document.Fields.Add($header,33)|Out-Null
    }
    # Retain the supplied university logo on the institutional cover only.
    $first=$document.Sections.Item(1)
    $first.PageSetup.DifferentFirstPageHeaderFooter=-1
    $headerIndex=$(if($reference.Sections.Item(1).PageSetup.DifferentFirstPageHeaderFooter){2}else{1})
    $first.Headers.Item(2).Range.FormattedText=$reference.Sections.Item(1).Headers.Item($headerIndex).Range.FormattedText
    $document.Repaginate();$document.Fields.Update()|Out-Null
    $document.Save()
    $document.ExportAsFixedFormat($PdfPath,17)
    Write-Output "APA document saved. Pages: $($document.ComputeStatistics(2))"
} catch {
    Write-Output $_.ScriptStackTrace
    throw
} finally {
    if($reference){$reference.Close(0);[Runtime.InteropServices.Marshal]::FinalReleaseComObject($reference)|Out-Null}
    if($document){$document.Close(0);[Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)|Out-Null}
    if($word){$word.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)|Out-Null}
}
