# VaultLink for Home Assistant

[![CI](https://github.com/alexhaberl/vaultlink-home-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/alexhaberl/vaultlink-home-assistant/actions/workflows/ci.yml)
[![Validate](https://github.com/alexhaberl/vaultlink-home-assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/alexhaberl/vaultlink-home-assistant/actions/workflows/validate.yml)

A local, read-only Home Assistant custom integration for monitoring a VaultLink
installation. It uses VaultLink's `monitoring:read` service-token scope and does
not expose buttons, services, switches, or any other write operation.

## Requirements

- Home Assistant 2026.8.0 or newer
- A reachable VaultLink server with the v2 monitoring API
- A VaultLink service token whose only required scope is `monitoring:read`

## Install with HACS

1. In HACS, open **Integrations**, choose **Custom repositories**, and add
   `https://github.com/alexhaberl/vaultlink-home-assistant` as an Integration.
2. Find **VaultLink**, choose **Download**, and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**, search for
   **VaultLink**, and complete the form.

For a manual installation, copy `custom_components/vaultlink` into the
`custom_components` directory of the Home Assistant configuration and restart
Home Assistant.

## Create a monitoring token

Create a service token in VaultLink with the `monitoring:read` scope. Copy it
when VaultLink displays it, then store it in a password manager. The integration
sends the token only in the `Authorization: Bearer …` header. It never uses a
query parameter and never publishes the token as an entity attribute or in
diagnostics.

No broader scope is required. A token without `monitoring:read` is rejected by
the setup flow.

## Configure the integration

The UI setup asks for:

- **VaultLink base URL** — an absolute HTTP or HTTPS root URL, for example
  `https://vaultlink.example.test`. Credentials, query strings, fragments, and
  subpaths are rejected.
- **Service token** — the token created above.
- **Verify TLS certificate** — enabled by default and strongly recommended.

The setup flow checks both liveness and the authenticated monitoring summary
with a ten-second HTTP timeout. The canonical root URL is the unique identifier,
so the same server cannot accidentally be configured twice.

The integration polls health, readiness, and summary every 60 seconds by
default. Change this under **Configure → Options** to any value from 30 to 3600
seconds. Redacted individual shares are polled every five minutes.

## Entities and devices

The main **VaultLink** device provides:

- a connectivity binary sensor for readiness;
- total, available, protected, inactive, expired, and download-limit-reached
  share counts;
- monthly download, ZIP-download, and preview counts; and
- free and total storage in bytes.

Each redacted share becomes a child device named `VaultLink Share #<id>` with a
status enum and, when present, an expiry timestamp. Download count, uploaded
bytes, uploaded files, and their configured maximum values are diagnostic
sensors disabled by default.

New shares are added automatically. If a share disappears from the monitoring
API, its existing entities become unavailable and remain in the entity registry
until an administrator explicitly removes them. At most 1,000 individual shares
are loaded per poll; aggregate summary sensors remain complete even when this
limit is exceeded, and diagnostics report `truncated: true`.

## TLS

Keep certificate verification enabled for HTTPS. If VaultLink uses a private
certificate authority, add that CA to the Home Assistant trust store instead of
disabling verification. The integration supports deliberately disabling the
check for a trusted local installation, but the setup UI and Home Assistant log
warn that this weakens transport security.

Plain HTTP is accepted for explicitly trusted local networks. Never send a
service token over an untrusted HTTP connection.

## Rotate or replace a token

If VaultLink returns HTTP 401 because a token expired or was revoked, Home
Assistant starts a reauthentication flow. Open the integration notification and
enter the replacement token. The URL and TLS setting remain unchanged.

To rotate proactively, replace/revoke the old token in VaultLink, then use the
reauthentication prompt after the next update. To change the server root URL or
TLS verification, use the integration's **Reconfigure** action.

## Failure handling and privacy

- Readiness HTTP 503 is valid readiness data: the connectivity sensor turns off
  without failing the entire coordinator.
- HTTP 401 triggers reauthentication; HTTP 403 identifies a missing scope.
- HTTP 429 honors `Retry-After` before one retry.
- Network and server failures mark coordinator entities unavailable and retain
  the last known values.
- Diagnostics contain API version, successful update times, aggregate summary,
  loaded-share count, and truncation state. The token, authorization header,
  full base URL, and individual share records are excluded or redacted.

## Development

The supported development runtime is Python 3.14.2. Install the test environment
and run all local checks with:

```bash
python -m pip install -e ".[test]"
ruff format --check .
ruff check .
mypy custom_components/vaultlink
pytest
```

GitHub Actions also run HACS validation and Home Assistant hassfest validation.

## License

MIT — see [LICENSE](LICENSE).
