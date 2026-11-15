# Windows review and live-demo guide

The user removed the presentation requirement. Use output/pdf/04-run-and-demo-guide.pdf for the first-launch checklist.

Open Demo.cmd, reset only rehearsal records, use a four-second delay, and start with the ground link unavailable.

## Three-minute live demonstration

**0:00-0:35.** Show Overview and identify the two due/overdue tasks. Open Maintenance,
review the intake task, check every step, enter `Demo Crew`, and record completion.
Show that its next due date changes and its completion appears below.

**0:35-1:05.** Open Spares inventory. Use one intake filter and enter
`Demo Crew - inspection`. Show the balance decrease. Explain that another window
cannot overwrite stock using an outdated balance.

**1:05-1:45.** Open Ground reports. Write `Airflow observation at Bay A2; training
scenario only.` Save it while the link is down. Point to `Queued locally`.
Restore the link. Show `Awaiting receipt`, then wait about eight seconds for
`Simulated receipt`. Explicitly state that the receiver is a local simulator.

**1:45-2:25.** In Demo & data, select `Low airflow warning`, apply, and return to
Overview. Allow two seconds for a sample and point to the warning. Return to Demo
& data, select `Corrupted airflow sample`, apply, and return to Overview. Explain
that the last valid value stays visible; after about 12 seconds it becomes stale.

**2:25-3:00.** Show Activity log and the rejected sample event. Download a database
backup. If time allows, exit and reopen Demo.cmd to show the completion and report
survive. Otherwise show restart persistence during questions using the same data.

## Optional failure demonstrations for questions

- Lost receipt: set link available and `Drop the next acknowledgement once`, save
  a new report, observe retry after eight seconds and a later single receipt.
- CSV rejection: import a file with a valid row followed by `NaN`. Explain that no
  row from that file is accepted. Then import a valid file with the required header.
- Inventory protection: attempt to use more stock than is available. The balance
  stays unchanged and a useful error appears.
- Recovery: close the app, use Restore backup.cmd, and reopen it. The old database
  is preserved in a recovery folder. Rehearse this separately from the timed demo.

## Demo recovery if something fails

If the display freezes, close and reopen the app. Saved records remain in SQLite.
If the app cannot open the database, preserve it, inspect the log, and restore a
verified backup using the recovery utility. If the demonstration PC fails, use
the saved screenshots and test output as fallback evidence and clearly say that
the live demonstration is unavailable. Never describe a screenshot as a live run.
