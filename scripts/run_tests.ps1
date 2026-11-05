$repoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "$repoRoot\src"
python -m unittest discover -s "$repoRoot\tests" -v

