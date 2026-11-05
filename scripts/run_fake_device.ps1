$repoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "$repoRoot\src"
python -m sitcp_host.testing.fake_rbcp @args
