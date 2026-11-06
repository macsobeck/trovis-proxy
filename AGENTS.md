# Repository Guidelines

## Project Structure & Module Organization

This Python 3.12 repository has two deliberately separate areas:

- `src/trovis_gateway/` is the generic communication gateway: Modbus framing, upstream transports, profile storage, admin API, and static UI.
- `src/trovis_manager/` is the read-only TROVIS 5573-1 FW 3.09 research and validation harness.
- `tests/gateway/`, `tests/unit/`, and `tests/integration/` mirror those responsibilities.
- `reference/` contains immutable inputs and derived firmware research; `docs/` records architecture and safety evidence.

Do not introduce controller model, firmware, or register semantics into `trovis_gateway`.

## Build, Test, and Development Commands

```bash
python -m pip install -e '.[dev,serial]'
pytest
ruff check .
trovis-gateway --config-path ./data/config.json
docker compose up --build
```

`pytest` uses fake local controllers; no default test may require hardware. `trovis-gateway` starts the proxy and local admin UI. Run `git diff --check` before committing.

## Coding Style & Naming Conventions

Use UTF-8, four-space indentation, Python type hints, and Ruff. Modules and functions use `snake_case`; classes use `PascalCase`; durations include units, for example `response_timeout_s`. Keep transport code asynchronous and controller-neutral. Preserve TROVIS terminology only in the research package.

## Testing Guidelines

Name tests after behavior, such as `test_write_timeout_is_not_retried`. Protocol changes require framing, malformed-input, timeout, retry, reconnect, Unit-ID translation, and opaque-function coverage. UI/API tests must prove secrets are masked and downstream infrastructure is not editable as a controller profile.

## Commit & Pull Request Guidelines

History uses short, capitalized, imperative subjects without trailing periods, for example `Add generic Modbus gateway`. Keep commits focused. Pull requests should explain scope and safety impact, link issues, list validation commands, and include screenshots for UI changes.

## Security & Protocol Safety

Never log or expose access keys. The current key mode is pass-through: store the value, but do not inject it. Transparent downstream write PDUs may be forwarded, but the gateway must never invent writes or retry one after an ambiguous result. Keep the research CLI read-only until its documented hardware gate passes.
