# Changelog

## 0.2.0

**Requires VaultLink 0.7.0 or newer. VaultLink 0.6.0 lacks the required
service-token monitoring API and is not supported. Upgrade VaultLink before
installing this integration.**

**Benötigt VaultLink ab 0.7.0. VaultLink 0.6.0 bietet die erforderliche
Monitoring-API mit Service-Tokens nicht und wird nicht unterstützt.
Vor der Installation dieser Integration zuerst VaultLink aktualisieren.**

- Read monthly activity from the monitoring API's `transfers` fields.
- Follow numeric share cursors, including installations with more than 200 shares.
- Keep other monitoring sensors available when storage capacity is unavailable.
- Read the total upload byte limit from `max_upload_total_size_bytes`.
- Cover the VaultLink 0.7.0 response format with regression tests.
