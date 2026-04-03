$root = Split-Path -Parent $PSScriptRoot
if (Test-Path "$root/.env") {
  Get-Content "$root/.env" | ForEach-Object {
    $key, $value = $_ -split "=", 2
    Set-Item -Path "Env:$key" -Value $value
  }
}
if ($env:SKILLS_VOTE_API_KEY) { "SKILLS_VOTE_API_KEY is set" } else { "SKILLS_VOTE_API_KEY is missing" }
