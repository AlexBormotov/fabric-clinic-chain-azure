---
id: PLAN-U11
spec: SPEC-001 / U11
owner: AlexBormotov
status: approach A taken 2026-10-28 under the owner's standing go-ahead
previous: PLAN-U15 (#12), PLAN-U09 (#16), PLAN-U13 (#15); see git history of this file
---

# PLAN-U11 — ADT replay producer

## Facts this plan rests on (read or measured 2026-10-28)

- `data/sources/adt/events.csv`: 13,125 events (A01/A02/A03), 2024-10-01 … 2026-09-30, written in
  event-time order with `event_id` 1…13,125. Contract: `docs/contracts/adt.yaml`.
- Event Hubs emulator (Microsoft Learn, "Test locally with the Event Hubs emulator" and "Event Hubs
  emulator overview", both `ms.date` 2026-08-25, read 2026-10-28):
  - image `mcr.microsoft.com/azure-messaging/eventhubs-emulator`; MCR tags read 2026-10-28 end at
    `2.2.1`, which is also `latest` (same manifest digest) and was built 2026-06-30 (`docker image
    inspect`); 2.2.0 was built 2026-01-07;
  - config mounted at `/Eventhubs_Emulator/ConfigFiles/Config.json`; one namespace, fixed name
    `emulatorNs1`; per event hub `Name`, `PartitionCount` (1–32), `ConsumerGroups` (1–20 items);
    `$Default` is created automatically and may not be listed (installer repo
    `Config-schema.json`, read 2026-10-28);
  - depends on Azurite: `BLOB_SERVER` and `METADATA_SERVER` both name the Azurite host; the
    upstream compose runs full Azurite (blob, queue, table ports); `ACCEPT_EULA=Y` required;
  - ports 5672 (AMQP), 9092 (Kafka), 5300 (`GET /health` → 200 `{"status":"healthy"}`); the image
    has no shell, so a compose healthcheck inside it is impossible;
  - connection string `Endpoint=sb://<host>;SharedAccessKeyName=RootManageSharedAccessKey;
    SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;` (a placeholder, not a secret);
  - entities and data do not survive a container restart; minimum retention 1 hour.
- `azure-eventhub` on PyPI (read 2026-10-28): latest 5.15.1, uploaded 2025-10-30; pure Python
  (pyAMQP), requires `azure-core`. `UseDevelopmentEmulator` is parsed in
  `azure/eventhub/_client_base.py`.
- Fabric Eventstream custom endpoint exposes an Event Hubs connection string with `EntityPath`;
  the producer takes it unchanged (cloud run in U20).

## Settings for every approach

- **Code:** `src/clinic_chain/adt_replay.py` (load, schedule, send), `scripts/replay_adt.py` (CLI).
  Arguments: `--rate` (events/s, default 50), `--late-share` (0.05), `--duplicate-share` (0.03),
  `--limit` (first N events), `--seed`, `--connection-string` or env
  `ADT_EVENTHUB_CONNECTION_STRING`, `--eventhub` (when the string has no `EntityPath`). Unset
  connection string means the local emulator.
- **Message:** body is the contract row as JSON (`event_id` int, the rest strings or null);
  application property `replay_seq` (send order). Partition key `clinic_id`, so each clinic's events
  stay ordered within a partition.
- **Schedule:** events sorted by (`event_time`, `event_id`). Exactly `round(late_share * n)` events
  are moved 1–20 positions later, always past an event with a strictly later `event_time`; exactly
  `round(duplicate_share * n)` events get a second copy 1–20 positions after the original. Each send
  is due at the running maximum `event_time` of the sends before it; wall time is
  `(due - first) / acceleration` with `acceleration = event-time span * rate / (sends - 1)`, so the
  replay keeps event-time gaps and hits the target rate on average. Due sends go out in one batch
  per clinic.
- **Compose:** services `eventhubs` (emulator 2.2.1, `config/eventhubs.json` mounted) and
  `eventhubs-azurite` (Azurite 3.37.0, all services); no host ports. `make up` starts them; the
  load script waits on `/health` before returning.
- **Tests:** fast unit tests on the schedule (exact late and duplicate counts, every late event
  passes a later one, copies follow originals, due times monotone, acceleration hits the rate).
  `stand` test: replay 2,000 events at 50/s into the emulator, read back from the partition
  positions taken before the replay, check all event ids, copies, rate from `enqueued_time` within
  ±10% and late and duplicate shares within ±1 pp.

## The choice: where late and duplicate events come from

### Approach A — producer-side reordering of a fixed schedule (taken)

The producer builds the whole send list up front with a seeded RNG, then paces it.

- Files: `src/clinic_chain/adt_replay.py`, `scripts/replay_adt.py`, `tests/test_replay.py`,
  `config/eventhubs.json`, `docker-compose.yml`, `Makefile`, `.env.example`, `pyproject.toml`,
  `uv.lock`, `README.md`, `CLAUDE.md`, `plan.md`.
- Invariants: every source event is sent at least once; body equals the contract row; shares are
  exact counts; same seed → same send list.
- Red checks: fast schedule tests; the stand test.
- Reverse: delete the new files, the two compose services and the Makefile target.

### Approach B — wall-clock jitter

Each event gets a random send delay; lateness and duplication emerge from the jitter.

- Shares are only approximate and depend on rate, so ±1 pp is not guaranteed; rejected.

### Approach C — Kafka protocol (port 9092)

- Same schedule, `confluent-kafka` instead of `azure-eventhub`. Adds a native dependency and the
  emulator supports only Kafka producer and consumer APIs; no gain over AMQP. Rejected.

## Implementation notes

- Stand test (2,000 events, 50/s, late 5%, duplicates 3%, seed 7), 2026-10-28: producer 2,060
  sends in 41.19 s (49.99/s, acceleration 225,959x); consumer received 2,000 distinct events plus
  60 copies, bodies equal to the contract rows, late share 0.0500, duplicate share 0.0300, rate
  from `enqueued_time` 50.55/s (+1.1%). Test 50 s including emulator start.
- Full file, schedule only: 13,125 events → 13,519 sends (656 late, 394 copies) built in 0.11 s;
  at 50/s the replay lasts 270 s.
- Negative control: allowing an anchor with an equal event time (`>=` for `>`) turns two fast
  tests red (measured late share 0.046 ≠ 0.05; a "late" event that no later event precedes).
  Restored; green.
- The stand test ran against the emulator alone (`docker compose up eventhubs-azurite eventhubs`):
  this worktree holds only `data/sources/adt/events.csv`, so `make up` (which also loads billing
  and FHIR) and the other `stand` tests run in CI only.
- No CI change: the `stand` job already runs `make up` and `make test-stand`, which now start the
  emulator and include the replay test (about 50 s more).
- In a git worktree `make secrets` scans 0 commits (`.git` is a file pointing outside the mount);
  the changed paths were scanned with `gitleaks dir` instead: no leaks. The emulator's
  `SAS_KEY_VALUE` placeholder needs no allowlist.
