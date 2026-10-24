# Changes

## 0.4.2 — 24 October 2026

- Move portal branding and administrator management together under Local Controls.
- Allow administrators to edit or hide the sign-in organization name.

## 0.4.1 — 24 October 2026

- Add default favicon and organization logo uploads in UniFi setup.
- Apply custom logos to login, sidebar and favicon; retain branding in appliance backups.

## 0.4.0 — 23 October 2026

- Data usage dashboard: highest-usage users, upload/download totals, period and user filters.
- Daily charts, monthly history, session usage and accounting freshness.
- Persistent incremental accounting ingestion with log backfill, cursor recovery and packet deduplication.
- Cumulative counter deltas, 64-bit gigawords, conservative reset handling and reporting time zones.
- Usage history stays in SQLite backups; no historical log-tail limit on the reporting database.

## 0.3.1 — 23 October 2026

- Link the sidebar Net2Net credit to https://www.net2net.co.za/ in a new tab.

## 0.3.0 — 23 October 2026

- Named administrator accounts with separate password hashes and sessions.
- Administrators page: add users, edit names, reset passwords and disable accounts.
- Change your own password with current-password verification and session revocation.
- Preserve the existing password and sessions while migrating password-only installations to the admin account.
- Prevent self-disable and strip credentials from validation error responses.

## 0.2.2 — 23 October 2026

- Wi-Fi user passwords now accept 7 or more characters in forms, API and imports.
- Administrator and network-device shared-secret requirements are unchanged.

## 0.2.1 — 23 October 2026

- Send an explicit server-plus-root certificate chain for Android Trust on First Use.
- Keep existing CA, keys, server certificate and fingerprint unchanged.

## 0.2.0 — 23 October 2026

- Import users, VLAN profiles and network devices from CSV or Excel.
- Full-system Excel workbook with profiles, users and devices sheets.
- Downloadable templates, preview with row errors and duplicate skip/update handling.
- Atomic imports with automatic recovery snapshot, stale-preview protection and one RADIUS reload.
- Credential values hidden in previews and error reports; upload/expanded workbook limits and formula rejection.
- Community Apps repository profile and portable first-install Docker template.

## 0.1.0 — 23 October 2026

- Initial UniFi RADIUS appliance: portal, users, profiles, devices, PEAP/MSCHAPv2, certificates, accounting and backups.
