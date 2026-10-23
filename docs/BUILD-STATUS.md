# Initial build — 23 October 2026

Deployed to Unraid host `172.17.10.38` as `net2net-unifi-radius`, using Docker `br0` and dedicated container IP `172.17.10.101`.

- Portal: http://172.17.10.101:8080
- RADIUS authentication: 172.17.10.101:1812 UDP
- RADIUS accounting: 172.17.10.101:1813 UDP
- Data: `/mnt/user/appdata/net2net-unifi-radius/data`
- Source: `/mnt/user/appdata/net2net-unifi-radius/source`
- Administrator password: local `.env` and server `source/.env` (excluded from source control and the Docker image).

Validated:

- Five API tests: authentication/CSRF header/logout, encrypted credential storage and VLAN policy, suspension, backup, invalid input, transactional rollback, login rate limiting and NAS/session ID collision handling.
- FreeRADIUS configuration validation on Debian with FreeRADIUS 3.2.7.
- Real UDP PAP and MSCHAP authentication with VLAN 3077 returned.
- Incorrect password and suspended-user rejection.
- Real UDP accounting response and report visible through the management API.
- Full PEAP/MSCHAPv2 exchange using eapol_test, with CA and server DNS-name validation enabled.
- Live appliance health endpoint and portal render.

Temporary smoke-test users, VLAN profiles and loopback NAS registrations are removed automatically. Smoke accounting reports remain as diagnostic history. No existing MikroTik data was copied.

Still requires site commissioning: register the actual UniFi AP/switch source IPs and shared secret, create matching VLANs and a test Enterprise SSID in UniFi, install the CA on a real client, and verify that client's VLAN and connectivity. The packet tests do not replace a real UniFi AP/client test.

Release repositories: [GitHub](https://github.com/Net2NetMain/Net2NetUniFiRadius) and [Docker Hub](https://hub.docker.com/r/botchris/net2netunifiradius). Images are built from this source; publishing requires authenticated registry access.
