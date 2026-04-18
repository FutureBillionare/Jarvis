# schedule_setup.ps1
# Creates a Windows Task Scheduler task that runs the internship workflow
# every morning at 8:00 AM.
#
# Run once as Administrator:
#   powershell -ExecutionPolicy Bypass -File schedule_setup.ps1

$taskName   = "HUBERT Internship Workflow"
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$jarvisRoot = (Get-Item $scriptPath).Parent.FullName
$pythonExe  = (Get-Command python).Source

$action  = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "-m internship_workflow.popup_server" `
    -WorkingDirectory $jarvisRoot

$trigger = New-ScheduledTaskTrigger -Daily -At "08:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# Remove old task if it exists
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed old task."
}

Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host "Task '$taskName' registered. Runs daily at 8:00 AM."
Write-Host "To run manually: Start-ScheduledTask -TaskName '$taskName'"
