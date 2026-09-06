# Changelog

## 0.2.0

**Requires VaultLink 0.7.0 or newer. If you still run VaultLink 0.6.0, stay on
integration 0.1.0 and upgrade VaultLink before updating this integration.**

**Erst ab VaultLink 0.7.0 kompatibel. Solange VaultLink 0.6.0 aktiv ist, bitte
bei Plugin-Version 0.1.0 bleiben und zuerst VaultLink aktualisieren.**

- Read monthly activity from the monitoring API's `transfers` fields.
- Follow numeric share cursors, including installations with more than 200 shares.
- Keep other monitoring sensors available when storage capacity is unavailable.
- Read the total upload byte limit from `max_upload_total_size_bytes`.
- Cover the VaultLink 0.7.0 response format with regression tests.
