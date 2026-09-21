# smtc_now.ps1 -- read the Windows System Media Transport Controls (SMTC) sessions
# and print one line of JSON on stdout.
#
# Used by the InkRealm backend (server/services/smtc.py) to detect the song that is
# currently playing in any SMTC-aware player (Spotify / 网易云音乐 / QQ音乐 / Edge /
# Chrome / PotPlayer / foobar2000 / Groove ...).
#
# Output shape:
#   {"ok":true,"sessions":[{"app":"","appId":"","title":"","artist":"","album":"",
#     "status":"Playing|Paused|Stopped","position":0.0,"duration":0.0,"playing":true}]}
#   {"ok":false,"error":"message"}
#
# Note: keep this file pure ASCII -- it is executed by Windows PowerShell 5.1 and
# non-ASCII bytes in a .ps1 without BOM get mis-decoded by the host.

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8

function Fail($msg) {
  $o = [ordered]@{ ok = $false; error = [string]$msg }
  Write-Output ($o | ConvertTo-Json -Compress -Depth 5)
  exit 0
}

try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null

  $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
  })[0]
  if ($null -eq $asTaskGeneric) { Fail 'AsTask(IAsyncOperation`1) not found' }

  function Await($op, $type) {
    $m = $asTaskGeneric.MakeGenericMethod($type)
    $task = $m.Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
  }

  # Project the WinRT types into the session before touching them.
  [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null
  [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null

  $mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
  if ($null -eq $mgr) { Fail 'session manager unavailable' }

  $list = @()
  foreach ($s in $mgr.GetSessions()) {
    $p = $null
    try { $p = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties]) } catch { }
    $info = $null
    try { $info = $s.GetPlaybackInfo() } catch { }
    $tl = $null
    try { $tl = $s.GetTimelineProperties() } catch { }

    $pos = 0.0
    $end = 0.0
    if ($null -ne $tl) {
      $pos = [double]$tl.Position.TotalSeconds
      $end = [double]$tl.EndTime.TotalSeconds
    }
    $status = ''
    if ($null -ne $info) { $status = [string]$info.PlaybackStatus }

    $list += [ordered]@{
      appId    = [string]$s.SourceAppUserModelId
      title    = $(if ($p) { [string]$p.Title } else { '' })
      artist   = $(if ($p) { [string]$p.Artist } else { '' })
      album    = $(if ($p) { [string]$p.AlbumTitle } else { '' })
      status   = $status
      playing  = ($status -eq 'Playing')
      position = [math]::Round($pos, 2)
      duration = [math]::Round($end, 2)
    }
  }

  $out = [ordered]@{ ok = $true; sessions = @($list) }
  Write-Output ($out | ConvertTo-Json -Compress -Depth 5)
} catch {
  Fail $_.Exception.Message
}
