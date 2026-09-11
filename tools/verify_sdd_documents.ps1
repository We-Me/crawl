param(
    [string]$PythonPath = 'python'
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command $PythonPath -ErrorAction SilentlyContinue)) {
    throw 'Python 3.9+ is required. Install it on PATH or pass -PythonPath with its executable path.'
}
if ($PSVersionTable.PSVersion -lt [version]'7.5') {
    throw 'PowerShell 7.5 or later is required for ConvertFrom-Json -DateKind String.'
}
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskSpec = Join-Path $taskRoot 'specs/001-public-knowledge-collection'
$taskContracts = Join-Path $taskSpec 'contracts'
if (-not (Get-Command Test-Json -ErrorAction SilentlyContinue)) {
    throw 'PowerShell 7 with Test-Json is required.'
}
function Test-DeclaredFormats {
    param([string]$JsonText, [string]$SchemaPath)
    $taskValue = $JsonText | ConvertFrom-Json -AsHashtable -DateKind String
    $taskSchemaValue = Get-Content -LiteralPath $SchemaPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable -DateKind String
    # All format-bearing fields in this set are top-level scalar properties.
    # Test-Json currently treats format as an annotation, so assert it explicitly.
    foreach ($taskField in $taskSchemaValue.properties.Keys) {
        $taskFieldSchema = $taskSchemaValue.properties[$taskField]
        if (-not $taskFieldSchema.ContainsKey('format') -or -not $taskValue.ContainsKey($taskField)) { continue }
        $taskFieldValue = $taskValue[$taskField]
        if ($null -eq $taskFieldValue) { continue }
        switch ($taskFieldSchema.format) {
            'date' {
                $taskParsedDate = [datetime]::MinValue
                if (-not [datetime]::TryParseExact([string]$taskFieldValue, 'yyyy-MM-dd', [cultureinfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$taskParsedDate)) { return $false }
            }
            'date-time' {
                if ([string]$taskFieldValue -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$') { return $false }
                $taskParsedTime = [datetimeoffset]::MinValue
                if (-not [datetimeoffset]::TryParse([string]$taskFieldValue, [cultureinfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$taskParsedTime)) { return $false }
            }
            'uri' {
                $taskParsedUri = $null
                if (-not [uri]::TryCreate([string]$taskFieldValue, [System.UriKind]::Absolute, [ref]$taskParsedUri)) { return $false }
                if ([string]::IsNullOrEmpty($taskParsedUri.Host) -or [string]$taskFieldValue -match '\s') { return $false }
            }
            default { throw "Unsupported format assertion: $($taskFieldSchema.format)" }
        }
    }
    return $true
}
function Confirm-Schema {
    param([string]$JsonText, [string]$SchemaName, [bool]$Expected, [string]$CaseName)
    $schemaPath = Join-Path $taskContracts "$SchemaName.schema.json"
    try {
        $actual = [bool](Test-Json -Json $JsonText -SchemaFile $schemaPath -ErrorAction Stop)
        if ($actual) { $actual = Test-DeclaredFormats $JsonText $schemaPath }
    } catch {
        if ($Expected) { throw "Schema validation error in $CaseName : $_" }
        $actual = $false
    }
    if ($actual -ne $Expected) { throw "Unexpected validation result: $CaseName" }
}
$taskCount = 0
$taskFiles = @{
    'manifest' = 'examples/data/manifests/crawl_manifest.jsonl'
    'document' = 'examples/data/normalized/documents.jsonl'
    'block' = 'examples/data/normalized/blocks.jsonl'
    'failure' = 'examples/data/manifests/failed_records.jsonl'
}
foreach ($taskType in $taskFiles.Keys) {
    foreach ($taskLine in Get-Content -LiteralPath (Join-Path $taskSpec $taskFiles[$taskType]) -Encoding utf8) {
        Confirm-Schema $taskLine $taskType $true "positive $taskType"
        $taskCount++
        $taskObject = $taskLine | ConvertFrom-Json -AsHashtable -DateKind String
        $taskSchema = Get-Content -LiteralPath (Join-Path $taskContracts "$taskType.schema.json") -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable -DateKind String
        foreach ($taskRequired in $taskSchema.required) {
            $taskBroken = $taskLine | ConvertFrom-Json -AsHashtable -DateKind String
            $taskBroken.Remove($taskRequired)
            Confirm-Schema (ConvertTo-Json $taskBroken -Depth 30 -Compress) $taskType $false "missing $taskRequired in $taskType"
            $taskCount++
        }
        if ($taskType -eq 'document' -and $taskObject.ContainsKey('attachments')) {
            foreach ($taskAttachment in $taskObject.attachments) {
                Confirm-Schema (ConvertTo-Json $taskAttachment -Depth 30 -Compress) 'attachment' $true 'positive attachment'
                $taskCount++
                $taskAttachment.Remove('raw_path')
                Confirm-Schema (ConvertTo-Json $taskAttachment -Depth 30 -Compress) 'attachment' $false 'downloaded attachment missing raw_path'
                $taskCount++
            }
        }
    }
}
$taskRegistry = Get-Content -LiteralPath (Join-Path $taskSpec 'examples/source-registry.json') -Raw -Encoding utf8
Confirm-Schema $taskRegistry 'source-registry' $true 'disabled source registry'
$taskCount++
$taskManifest = Get-Content -LiteralPath (Join-Path $taskSpec $taskFiles.manifest) -Encoding utf8 | Select-Object -First 1 | ConvertFrom-Json -AsHashtable -DateKind String
$taskManifest.discovery_method = 'search'
Confirm-Schema (ConvertTo-Json $taskManifest -Depth 30 -Compress) 'manifest' $false 'search requires keyword'
$taskManifest.keyword = '边境'
Confirm-Schema (ConvertTo-Json $taskManifest -Depth 30 -Compress) 'manifest' $true 'search with keyword'
$taskCount += 2
$taskBlock = @{block_id='TABLE1';doc_id='DEMO_D1';order=0;block_type='table';extraction_method='xlsx';structured_data=@{columns=@('name');rows=@(@('value'))}}
Confirm-Schema (ConvertTo-Json $taskBlock -Depth 30 -Compress) 'block' $true 'table structured data without text'
$taskBlock.structured_data = @{}
Confirm-Schema (ConvertTo-Json $taskBlock -Depth 30 -Compress) 'block' $false 'empty table data and no text'
$taskBlock.block_type = 'paragraph'
Confirm-Schema (ConvertTo-Json $taskBlock -Depth 30 -Compress) 'block' $false 'paragraph missing text'
$taskCount += 3
$taskDocument = Get-Content -LiteralPath (Join-Path $taskSpec $taskFiles.document) -Encoding utf8 | Select-Object -First 1 | ConvertFrom-Json -AsHashtable -DateKind String
$taskDocument.full_text = ''
Confirm-Schema (ConvertTo-Json $taskDocument -Depth 30 -Compress) 'document' $false 'ok document empty full_text'
$taskDocument.parse_status = 'partial'
Confirm-Schema (ConvertTo-Json $taskDocument -Depth 30 -Compress) 'document' $true 'partial preserves empty extraction'
$taskDocument.raw_path = '../outside.html'
Confirm-Schema (ConvertTo-Json $taskDocument -Depth 30 -Compress) 'document' $false 'parent path escape'
$taskCount += 3
$taskManifest.crawl_time = 'not-a-time'
Confirm-Schema (ConvertTo-Json $taskManifest -Depth 30 -Compress) 'manifest' $false 'date-time format assertion'
$taskCount++
$taskDocument.raw_path = 'raw/demo.html'
$taskDocument.publication_date = '2026-02-30'
Confirm-Schema (ConvertTo-Json $taskDocument -Depth 30 -Compress) 'document' $false 'invalid calendar date'
$taskDocument.publication_date = '2026-02-28'
Confirm-Schema (ConvertTo-Json $taskDocument -Depth 30 -Compress) 'document' $true 'valid calendar date'
$taskDocument.source_url = 'https://'
Confirm-Schema (ConvertTo-Json $taskDocument -Depth 30 -Compress) 'document' $false 'missing URI host'
$taskCount += 3
Write-Output "JSON Schema checks PASS: $taskCount positive and negative cases, using Test-Json plus explicit date/time/URI assertions."
& $PythonPath (Join-Path $PSScriptRoot 'verify_sdd_documents.py')
if ($LASTEXITCODE -ne 0) { throw 'Structural verification failed.' }
