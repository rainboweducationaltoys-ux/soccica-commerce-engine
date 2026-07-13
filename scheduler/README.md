# Weekly scheduler (launchd)

Runs `run.sh` (the full pipeline: `run_pipeline.py` then `publish_final_products.py`)
once a week, every **Monday at 02:00**, using macOS `launchd`.

`launchd`'s `Weekday` key uses `0`/`7` = Sunday, `1` = Monday, ... `6` = Saturday
(per `man launchd.plist`) — the plist here uses `1` for Monday.

## Activate it (run these yourself in Terminal)

```
cp scheduler/com.soccica.weekly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.soccica.weekly.plist
```

Check it's registered:

```
launchctl list | grep soccica
```

## Where output goes

- `logs/scheduler_stdout.log` / `logs/scheduler_stderr.log` — whatever `run.sh`
  printed to stdout/stderr for that run. Check this first to confirm launchd
  actually fired the job.
- `logs/app.log` / `logs/errors.log` — the pipeline's own application-level logging
  (see `src/logging_setup.py`). Check this to see what the pipeline itself did/found.

If `scheduler_stdout.log` has nothing new after a Monday 02:00 has passed, launchd
never ran the job (see the sleep/wake note below). If it has output but `app.log`
looks wrong, the problem is in the pipeline itself, not the scheduling.

## Disable / remove it later

```
launchctl unload ~/Library/LaunchAgents/com.soccica.weekly.plist
rm ~/Library/LaunchAgents/com.soccica.weekly.plist
```

## Important: the Mac must be awake at 02:00 Monday

`launchd` `StartCalendarInterval` jobs only fire if the Mac is awake (or wakes on
its own, e.g. plugged in with power-nap-style scheduled wake) at the scheduled
time. If it's asleep or shut down at 02:00 Monday, **the run is skipped, not
queued** — it won't catch up later.

If you want the Mac to reliably wake for this, you can schedule a wake (requires
your admin password — run this yourself, not something to automate):

```
sudo pmset repeat wakeorpoweron MTWRFSU 02:00:00
```

Note: macOS's `pmset repeat` doesn't support a single-day-only wake schedule, so
this wakes the Mac at 02:00 **every day**, not just Monday. That's harmless — the
plist above still only actually runs `run.sh` on Mondays, so on the other 6 days
the Mac just briefly wakes up and goes back to sleep with nothing happening.
