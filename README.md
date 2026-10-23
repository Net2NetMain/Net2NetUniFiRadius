# Net2Net UniFi RADIUS

Independent UniFi edition derived from [Net2NetRadius](https://github.com/Net2NetMain/Net2NetRadius). Version 0.3.1. The parent MikroTik application and its data are not changed.

Source: [Net2NetUniFiRadius](https://github.com/Net2NetMain/Net2NetUniFiRadius). Container: [botchris/net2netunifiradius](https://hub.docker.com/r/botchris/net2netunifiradius). Release tags: `0.3.1` and `latest`.

## Import CSV / Excel

Open **Import data**, or click **Import** on Wi-Fi users, VLAN profiles or Network devices. Download a template, fill in the records, select your file, and click **Preview import**. Review errors, counts, record names and policies, then click **Import these records**. Nothing is saved during preview. If the file, options or existing records change, preview again.

- CSV: UTF-8, comma/semicolon/tab separated. Select users, profiles or devices. Excel `.xlsx`: use matching sheet names; choose **Full system** to process all three sheets. Older `.xls` files must be saved as `.xlsx`.
- Users: `username,display_name,password,profile,vlan,status`. New users require a password (7+ printable ASCII characters); display name defaults to username and status to active. A missing profile is automatically created when a valid VLAN is included. For an existing profile, leave VLAN blank or match it exactly.
- Profiles: `name,vlan` (VLAN 1–4094). Devices: `name,address,secret` (16+ characters using letters, numbers, underscore, dot, ! @ # or hyphen).
- **Skip existing** is the default. **Update matching** matches usernames or profile/device names. Blank passwords/shared secrets retain existing credentials. Other fields replace existing values; blank user status becomes active. No records are deleted.
- The entire batch must validate. Imports are atomic and reload RADIUS once. An encrypted database snapshot is saved to `/data/imports/before-import-*.sqlite` before applying; keep the existing `/data/secret.key` to recover it. These local snapshots are not rotated automatically.
- Limit: 8 MB upload, 5,000 data rows total, 30 columns per sheet, 50 MB expanded workbook. Formula cells are rejected; paste values instead. Unknown workbook sheets are ignored.

Full-system workbook import covers users, profiles and network devices. It preserves this installation's administrator login, certificates and accounting history. Use full appliance backups for a byte-for-byte migration including those files. Upload files are processed in memory; they are not retained, and credentials are hidden in previews. Protect source exports because they contain credentials.

## First release

- Local administrator portal; Wi-Fi user create/edit/delete and access status.
- VLAN profiles and per-device RADIUS source IP/shared secret registration.
- FreeRADIUS PEAP/MSCHAPv2 enterprise Wi-Fi authentication, PAP/CHAP for diagnostics.
- Standard VLAN attributes: Tunnel-Type 13, Tunnel-Medium-Type 6, Tunnel-Private-Group-Id.
- Persistent private CA and server certificate; authenticated CA download.
- Accounting detail logs and recent session reports; downloadable database/key/certificate backup.
- Encrypted stored Wi-Fi passwords and device secrets, hashed administrator password, expiring sessions.

This release does not automate the UniFi controller, guest portals, MAC authentication, CoA disconnects, billing or speed limits. Suspend/disable denies the next authentication; existing clients require reauthentication or reconnection. Editing records briefly restarts FreeRADIUS to load both users and NAS clients. EAP session resumption is disabled to avoid bypassing changed access policies.

See [initial build verification](docs/BUILD-STATUS.md) for test results. The [Unraid template](unraid/net2net-unifi-radius.xml) points to the Docker Hub image.

## Run with Docker

Copy `.env.example` to `.env`, set a unique ADMIN_PASSWORD (12+ characters), and choose the certificate DNS name before the first start. Then:

```sh
docker compose up -d --build
```

Open `http://SERVER-IP:8088`. Sign in with username `admin` and ADMIN_PASSWORD. ADMIN_PASSWORD initializes an empty database only. Updating the environment does not reset an existing password. Older password-only installations migrate automatically to the `admin` account with their existing password and active sessions preserved.

## Administrator accounts

Open **Administrators** to add named administrator accounts, manage display names, enable/disable accounts or reset another administrator's password. All administrators have full appliance access. Each account has a separate salted password hash and separate sessions; passwords are never shown in account lists.

Use **Change my password** to change your own password. Account changes require your current administrator password. Administrator passwords require 12 or more characters; the 7-character Wi-Fi user minimum is separate. Changing your password signs out all your sessions. Resetting another administrator's password or disabling their account signs out their sessions. You cannot disable your own account, so at least one active administrator remains.

An initial password is assigned when adding an administrator. Give the username/password to that administrator through your normal secure channel; they can change it after signing in. Keep the full appliance backup for recovery. The Docker bootstrap variable does not override account passwords after initialization.

On Unraid without Compose:

```sh
docker pull botchris/net2netunifiradius:latest
docker run -d --name net2net-unifi-radius --restart unless-stopped \
  --network br0 --ip YOUR_UNUSED_LAN_IP \
  --env-file .env \
  -v /mnt/user/appdata/net2net-unifi-radius/data:/data \
  --label net.unraid.docker.managed=dockerman \
  --label 'net.unraid.docker.webui=http://[IP]:[PORT:8080]' \
  botchris/net2netunifiradius:latest
```

Replace `YOUR_UNUSED_LAN_IP` with an unused address on your own LAN. With a dedicated `br0` address, open `http://YOUR_UNUSED_LAN_IP:8080`; RADIUS uses that address on UDP ports `1812` and `1813`. No host port mappings are needed on br0. For Compose, set `UNIFI_RADIUS_IP` in your local `.env` file, then use `docker compose -f compose.unraid.yaml up -d --build`. No address is supplied by default. The generic `compose.yaml` remains a portable Docker bridge example.

Check for occupied ports first. If another RADIUS service uses 1812/1813, choose different host ports and enter those in UniFi. Keep the administrator portal on a trusted management network; use an HTTPS reverse proxy for remote access. The bootstrap password and Wi-Fi/shared secrets must never be committed to GitHub or baked into the image.

## UniFi commissioning

1. Create the desired VLANs in UniFi; carry those VLANs on AP/switch uplinks.
2. Create matching VLAN profiles in this portal.
3. Register the actual RADIUS packet source IP of each AP/switch; do not assume the controller sends authentication requests. Use the same shared secret in UniFi. This release requires Message-Authenticator; use current device firmware.
4. Configure an external RADIUS profile with this server's reachable IP, UDP auth/accounting ports, shared secret, RADIUS-assigned VLAN support, and accounting (300-second interim updates).
5. Create a test WPA2 Enterprise SSID with that RADIUS profile. Start with PEAP/MSCHAPv2.
6. Download the CA from the portal. Configure clients to trust it and validate the server certificate name (default `radius.net2net.local`). Do not disable server validation.
7. Add a test user and confirm a real Wi-Fi login, assigned VLAN and accounting records. Repeat with a wrong password and a suspended user.

References: [Ubiquiti RADIUS setup](https://help.ui.com/hc/en-us/articles/360015268353-Configuring-a-RADIUS-Server-in-UniFi), [FreeRADIUS EAP configuration](https://github.com/FreeRADIUS/freeradius-server/blob/v3.2.x/raddb/mods-available/eap).

The private CA lasts 10 years; the server certificate lasts 825 days. Renewal is currently manual. Keep the certificate DNS name stable. These are Wi-Fi EAP certificates, not HTTPS certificates for the management portal. This release targets WPA2 Enterprise PEAP; WPA3 Enterprise and RadSec have not been commissioned.

## Backup / restore

The portal downloads a ZIP with `unifi.db`, `secret.key` and `certs/`. It contains private keys and recoverable network credentials: keep it protected. To restore, stop the container, copy the archive contents into its mapped data directory, and restart. Keep the original data directory as a rollback copy. Accounting history is kept separately in `data/accounting/`; copy the full stopped data directory to preserve it. Log retention and certificate renewal automation are future work.

## Local development

Python 3.12+:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
$env:ADMIN_PASSWORD = 'your-unique-local-admin-password'
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8088
```

Local Windows mode runs the portal/API without FreeRADIUS. The UI explicitly labels it as a local preview. The Docker build runs the full service. Run tests with `python -m pytest` from this directory. No production accounts, PPPoE exports, or parent database are imported.

Full RADIUS integration test (run after the appliance is healthy):

```sh
docker build -t net2net-unifi-radius:local .
docker build -f tests/Dockerfile -t net2net-unifi-radius-test:local .
docker run --rm --network container:net2net-unifi-radius --env-file .env \
  -v /mnt/user/appdata/net2net-unifi-radius/data/certs:/data/certs:ro \
  net2net-unifi-radius-test:local
```

This creates temporary records, tests PEAP/MSCHAPv2, PAP, VLAN replies, accounting and suspension, then removes those records. It requires the initial administrator password to still match `.env` and no existing loopback NAS registration. Keep this test image separate from the runtime image.
