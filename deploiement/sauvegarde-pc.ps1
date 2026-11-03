# Sauvegarde de la base en ligne (Render) sur votre PC Windows.
# Prérequis : installer PostgreSQL (outils client) https://www.postgresql.org/download/windows/
# Usage (PowerShell) :  .\deploiement\sauvegarde-pc.ps1 "postgresql://...External Database URL..."
# L'« External Database URL » se trouve sur Render → talaouglid-db → Connect → External.
param([Parameter(Mandatory=$true)][string]$UrlBase)
$dossier = "$HOME\Documents\Sauvegardes-Talaouglid"
New-Item -ItemType Directory -Force -Path $dossier | Out-Null
$fichier = "$dossier\talaouglid-$(Get-Date -Format 'yyyy-MM-dd').dump"
pg_dump --format=custom --no-owner --dbname="$UrlBase" --file="$fichier"
if ($LASTEXITCODE -eq 0) { Write-Host "Sauvegarde créée : $fichier" } else { Write-Host "Échec de la sauvegarde" -ForegroundColor Red }
# Restaurer dans une base vide :  pg_restore --no-owner --dbname="URL_NOUVELLE_BASE" "$fichier"
