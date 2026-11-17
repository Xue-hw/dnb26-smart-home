#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$reportDirectory = Join-Path $projectRoot 'output\acceptance\time-sync'
$serverKey = 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpServer'
$configKey = 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Config'
$ruleName = 'DnB26-LAN-NTP-OrangePi'
$localAddress = '192.168.137.1'
$boardAddress = '192.168.137.2'

Write-Host '[1/5] Checking the dedicated Ethernet address and existing firewall rule...'
$adapterAddress = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $localAddress
if (@($adapterAddress).Count -ne 1) { throw 'The dedicated Orange Pi IPv4 address is not unique.' }
$timeService = Get-Service W32Time
$existingRule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existingRule) {
    $addressFilter = $existingRule | Get-NetFirewallAddressFilter
    $portFilter = $existingRule | Get-NetFirewallPortFilter
    $interfaceFilter = $existingRule | Get-NetFirewallInterfaceFilter
    if ($existingRule.Direction -ne 'Inbound' -or $existingRule.Action -ne 'Allow' -or
        $existingRule.Enabled -ne 'True' -or
        @($addressFilter.LocalAddress).Count -ne 1 -or $addressFilter.LocalAddress -ne $localAddress -or
        @($addressFilter.RemoteAddress).Count -ne 1 -or $addressFilter.RemoteAddress -ne $boardAddress -or
        $portFilter.Protocol -ne 'UDP' -or $portFilter.LocalPort -ne '123' -or
        @($interfaceFilter.InterfaceAlias).Count -ne 1 -or $interfaceFilter.InterfaceAlias -ne $adapterAddress.InterfaceAlias) {
        throw 'A different firewall rule already uses the DnB26 rule name; inspect it before continuing.'
    }
}

Write-Host '[2/5] Saving the original Windows Time settings...'
New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
$backupPath = Join-Path $reportDirectory 'windows-before.json'
if (-not (Test-Path -LiteralPath $backupPath)) {
    $before = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        ntp_server_enabled = (Get-ItemProperty -LiteralPath $serverKey).Enabled
        announce_flags = (Get-ItemProperty -LiteralPath $configKey).AnnounceFlags
        service_start_type = $timeService.StartType.ToString()
        service_status = $timeService.Status.ToString()
        firewall_rule_existed = [bool]$existingRule
        local_address = $localAddress
        board_address = $boardAddress
    }
    $before | ConvertTo-Json | Set-Content -LiteralPath $backupPath -Encoding UTF8
}

# Preserve the computer's existing upstream time source and time zone.
Write-Host '[3/5] Enabling Windows Time and the board-only NTP firewall rule...'
Set-ItemProperty -LiteralPath $serverKey -Name Enabled -Value 1
Set-ItemProperty -LiteralPath $configKey -Name AnnounceFlags -Value 5
Set-Service W32Time -StartupType Automatic
if (-not $existingRule) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'DnB26 Orange Pi LAN time only' `
        -Direction Inbound -Action Allow -Enabled True -Profile Any `
        -InterfaceAlias $adapterAddress.InterfaceAlias -LocalAddress $localAddress `
        -RemoteAddress $boardAddress -Protocol UDP -LocalPort 123 | Out-Null
}
Start-Service W32Time
Write-Host '[4/5] Refreshing Windows Time and checking UDP 123...'
& w32tm.exe /config /update
if ($LASTEXITCODE -ne 0) { throw 'Windows Time configuration refresh failed.' }
Restart-Service W32Time
Start-Sleep -Seconds 2
if ((Get-Service W32Time).Status -ne 'Running') { throw 'Windows Time did not start.' }
Get-NetUDPEndpoint -LocalPort 123 -ErrorAction Stop | Out-Null

[ordered]@{
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
    result = 'windows_lan_time_server_running'
    local_address = $localAddress
    allowed_client = $boardAddress
    upstream_configuration_changed = $false
    timezone_changed = $false
    backup = $backupPath
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $reportDirectory 'windows-after.json') -Encoding UTF8

Write-Host '[5/5] Windows LAN time source is ready; configuring Orange Pi over SSH (sudo may ask for a password)...'
$remoteSetup = '/home/HwHiAiUser/projects/dnb26-smart-home/shared/time-sync/enable_lan_time_board.sh'
& ssh.exe -t orangepi-aipro "sudo /bin/bash $remoteSetup"
if ($LASTEXITCODE -ne 0) { throw 'Orange Pi time setup did not finish; keep the terminal error for diagnosis.' }
Write-Host 'DnB26 automatic LAN time synchronization is configured.'
