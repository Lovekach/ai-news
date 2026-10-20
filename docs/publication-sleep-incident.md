# Missed publication: October 19, 2026

## Findings

The failure occurred before the publisher process started. It was not an empty
edition, Telegram rejection, uncertain delivery or a ledger conflict.

All times below are Europe/Moscow:

| Time | Evidence |
| --- | --- |
| October 19, 18:00:01–18:02:39 | Editor log records a successful run and exit 0. |
| 18:00:57, 18:01:47, 18:02:34 | SQLite audit records three transitions to `ready`. |
| 20:09:18 | Last completed collector run before the overnight gap. |
| 20:09:42 | Windows Kernel-Power event 506: Modern Standby entry, reason `Lid`. |
| 20:15 / 20:50 / 21:00 | No editor/publisher runner-start entries. |
| October 20, 05:44:49 | Kernel-Power event 507: next recorded exit from standby. |
| 05:44:52–05:44:54 | Collectors resume; deferred editor exits without LLM outside its evening window. |

The existing publisher and editor definitions had no enabled `WakeToRun`.
The active Windows power scheme also disabled wake timers on both AC and DC.
The publisher's last task result, `0x800710E0` (request refused), belongs to the
October 20 05:44 recorded attempt. It must not be presented as a Telegram error
or as a captured Task Scheduler event at 21:00. Task Scheduler Operational
history is disabled at diagnosis, so its historical trigger/refusal event is absent.
System events and the independent application-log gap establish the sleep
failure chain; they do not supply the missing Task Scheduler history.
The Security log was inaccessible to this diagnostic session, so an independent
sign-out determination is unavailable. The session log had no matching events.
No Python application-crash events were found in the 20:00–21:10 interval.

`daily:2026-10-19` has no digest or membership rows. There are no `sending` or
`send_uncertain` items in the incident snapshot. The existing code reserves
the ledger before sending; this path did not issue a send request. The persistent
`editor.lock` filename is normal: byte-range locks are released with their owning
handle. A lock check occurs after runner startup, which was never recorded.
Deleting that file or resetting the ledger would not address the incident.

A read-only composition replay used the pre-incident production code and an
isolated snapshot: three candidates, three selected stories, 2,356 UTF-16 units,
no final-gate exclusions. This is a reconstruction from saved drafts/audit, not
a historical send attempt. The original source fields and production database
were not edited. Current read-only Bot API checks confirmed readable credentials,
the expected bot, configured channel and posting permission; they cannot prove
network availability during the missed night.

PR #11 was installed after the incident. Its continuous coverage fix does not
cause or resolve a Windows sleep/start failure. Experimental PRs #9/#10 remain
outside production.

## Operator decision, changes and unresolved availability

The owner explicitly prohibited automatic laptop wake-up. A prepared wake-only
proposal was withdrawn before publication or deployment. No wake-capable task,
power-policy change or wake-up experiment was applied. The installer now
explicitly sets `WakeToRun=false` for every AI News job; contributor instructions
preserve this decision for future changes. Existing task definitions stay intact.

Started publisher invocations now explain their preflight refusals: automatic
publishing disabled, missing destination, outside the publication window or
an existing receipt. These messages distinguish intentional refusal from an
empty edition or a send failure. They cannot log a task that Windows never
started and do not fix the host's sleep-related unavailability.

Offline tests use temporary files/databases and mocked process/Telegram calls.
They exercise the actual installer function's no-wake policy, HTTP rejection,
runner timeout, process-launch refusal, interruption after reservation and the
explicit preflight messages. Existing tests retain normal 21:00 publishing,
empty editions, uncertain delivery and duplicate prevention. A denied child
process launch is a control of runner error handling, not reproduction of a
Windows Scheduler trigger failure. No physical sleep/wake experiment is run.

**The availability incident is diagnosed, but recurrence while the laptop sleeps
is not eliminated.** With automatic wake prohibited, this local installation can
publish at 21:00 only when the host is awake, the user is logged in, and verified
news/network access are available. The time of the next configured trigger is
not proof that the machine will execute it. No historical resend, test-channel
message, new sender, model change or ledger reset is part of this change.
