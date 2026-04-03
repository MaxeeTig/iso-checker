# ISO checker — SVFE Host2Host partner simulator

Python service that simulates the **SmartVista / processing-center** side of Host2Host ISO 8583 so acquiring partners can test against the protocol before live integration.

See **limitations** and usage in this file after the first release; scenario authoring is in `SCENARIOS.md`. Full field reference: `docs/SVFE_Host2Host_AI_INDEX.md`.

## Quick start (development)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/iso-checker serve --scenario-file scenarios/default.yaml --port 8583
```

Validate YAML only:

```bash
.venv/bin/iso-checker validate-scenarios scenarios/default.yaml
```

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

Optional: `--reversal` sends **1420** after a successful **1110** (same TCP session; uses RRN from the response). See `scripts/client_send_auth.py --help` for PAN, amount, STAN, and Field 48 tag 002.

## v1 limitations

- **No MAC verification** (DE64/DE128), no PIN/crypto/key exchange enforcement. DE52/55 may be parsed as binary blobs only.
- **Protocol and scenario checks only** — not full SmartVista business rules.
- **PCI:** logs mask PANs; never log PIN/CVV/track data.

## Partner diagnostics

Use `--log-level DEBUG` for safe field dumps. Use `--report run.jsonl` for JSON Lines events (`validation_fail`, `scenario_fail`, etc.). Error codes are listed in `SCENARIOS.md`.
