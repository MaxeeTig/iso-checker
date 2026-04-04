# ISO checker — SVFE Host2Host partner simulator

Python service that simulates the **SmartVista / processing-center** side of Host2Host ISO 8583 so acquiring partners can test against the protocol before live integration.

See **limitations** and usage in this file after the first release; scenario authoring is in `SCENARIOS.md`. Full field reference: `docs/SVFE_Host2Host_AI_INDEX.md`.

## Quick start (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
python -m iso_checker.cli serve --scenario-file scenarios/default.yaml --port 8583
```

Validate YAML only:

```bash
python -m iso_checker.cli validate-scenarios scenarios/default.yaml
```

Initialize the SQLite database and bootstrap an admin user:

```bash
python -m iso_checker.cli init-db --db-path var/iso_checker.sqlite3 --admin-username admin --admin-password admin
```

Run the simulator together with the partner portal:

```bash
python -m iso_checker.cli serve-app \
  --scenario-file scenarios \
  --db-path var/iso_checker.sqlite3 \
  --port 8583 \
  --http-port 8080
```

The portal will be available on `http://127.0.0.1:8080` by default.
Scenario catalog entries are built from all `*.yaml` / `*.yml` files in the configured directory.

Docker (see also `docker-compose.example.yml`):

```bash
docker build -t iso-checker .
docker run --rm -p 8583:8583 -v "$PWD/scenarios:/app/scenarios:ro" iso-checker \
  serve --scenario-file /app/scenarios/default.yaml --scenario-name auth_reversal
```

Generate a JSON Lines trace for support:

```bash
iso-checker serve --scenario-file scenarios/default.yaml --report ./run.jsonl
```

### Client test script (partner workstation)

From repo root with venv active:

```bash
python scripts/client_send_auth.py --host <simulator-host> --port 8583
```

If you prefer the console script after installation, `iso-checker ...` still works. The `python -m iso_checker.cli ...` form is documented here because it is the more familiar Python workflow for many teams.

Run a predefined full scenario as the client:

```bash
python scripts/client_run_scenario.py --host 127.0.0.1 --port 8583 --scenario auth_reversal
```

Optional: `--reversal` sends **1420** after a successful **1110** (same TCP session; uses RRN from the response). See `scripts/client_send_auth.py --help` for PAN, amount, STAN, and Field 48 tag 002.

## Portal features

- Built-in login with SQLite-backed users
- Company/partner records with expected DE32 / DE41 / DE42 matching
- Scenario run history and per-message timelines
- Admin pages for company and user creation
- Browser-triggered execution of predefined client scenario scripts

## v1 limitations

- **No MAC verification** (DE64/DE128), no PIN/crypto/key exchange enforcement. DE52/55 may be parsed as binary blobs only.
- **Protocol and scenario checks only** — not full SmartVista business rules.
- **PCI:** logs mask PANs; never log PIN/CVV/track data.

## Partner diagnostics

Use `--log-level DEBUG` for safe field dumps. Use `--report run.jsonl` for JSON Lines events (`validation_fail`, `scenario_fail`, etc.). Error codes are listed in `SCENARIOS.md`.
