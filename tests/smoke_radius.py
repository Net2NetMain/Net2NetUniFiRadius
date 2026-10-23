"""Run inside the appliance: API, real RADIUS PAP/MSCHAP, VLAN and accounting.

Creates and removes isolated temporary records. No user device is required.
"""
import json
import os
import secrets
import subprocess
import urllib.request
import http.cookiejar
import csv
import io

jar = http.cookiejar.CookieJar()
http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def api(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request('http://127.0.0.1:8080/api/' + path, data=data,
        method=method, headers={'Content-Type': 'application/json', 'X-Net2Net-Request': 'portal'})
    with http.open(request, timeout=30) as response:
        return json.load(response)


def radius(username, password, secret, expected, mode='pap'):
    result = subprocess.run(['radtest', '-t', mode, username, password,
                             '127.0.0.1', '0', secret], capture_output=True, text=True, timeout=20)
    assert expected in result.stdout, result.stdout + result.stderr
    if expected == 'Access-Accept':
        assert 'Tunnel-Private-Group-Id:0 = "3077"' in result.stdout or 'Tunnel-Private-Group-Id = "3077"' in result.stdout, result.stdout
    return result.stdout


def run():
    api('login', {'password': os.environ['ADMIN_PASSWORD']})
    suffix = secrets.token_hex(4)
    profile_id = user_id = nas_id = None
    secret = secrets.token_hex(16)
    password = 'Smoke-%{literal}-' + secrets.token_hex(8)
    username = 'smoke-' + suffix
    try:
        api('profiles', {'name': 'Smoke ' + suffix, 'vlan': 3077})
        profile_id = next(p['id'] for p in api('state')['profiles'] if p['name'] == 'Smoke ' + suffix)
        api('nas', {'name': 'Smoke loopback ' + suffix, 'address': '127.0.0.1', 'secret': secret})
        nas_id = next(p['id'] for p in api('state')['nas'] if p['address'] == '127.0.0.1')
        body = {'username': username, 'display_name': 'Temporary smoke test',
                'password': password, 'profile_id': profile_id, 'status': 'active'}
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['username', 'display_name', 'password', 'profile', 'vlan', 'status'])
        writer.writerow([username, body['display_name'], password, 'Smoke ' + suffix, 3077, 'active'])
        content = output.getvalue().encode()
        def import_request(stage, token=None):
            request = urllib.request.Request('http://127.0.0.1:8080/api/import/' + stage +
                '?filename=smoke.csv&kind=users&duplicates=skip', data=content,
                headers={'Content-Type': 'application/octet-stream', 'X-Net2Net-Request': 'portal',
                         **({'X-Import-Preview': token} if token else {})})
            with http.open(request, timeout=30) as response:
                return json.load(response)
        preview = import_request('preview')
        assert preview['valid'], preview
        assert import_request('apply', preview['token'])['applied']
        print('PASS: CSV import preview and atomic apply')
        user_id = next(p['id'] for p in api('state')['users'] if p['username'] == username)
        radius(username, password, secret, 'Access-Accept')
        print('PASS: PAP authentication and VLAN 3077')
        radius(username, password, secret, 'Access-Accept', 'mschap')
        print('PASS: MSCHAP authentication and VLAN 3077')
        radius(username, 'wrong-password', secret, 'Access-Reject')
        print('PASS: incorrect password rejected')
        attrs = f'User-Name = "{username}"\nAcct-Session-Id = "{suffix}"\nAcct-Status-Type = Start\nNAS-IP-Address = 127.0.0.1\n'
        result = subprocess.run(['radclient', '-x', '127.0.0.1:1813', 'acct', secret],
                                 input=attrs, text=True, capture_output=True, timeout=20)
        assert 'Accounting-Response' in result.stdout, result.stdout + result.stderr
        assert any(s['session_id'] == suffix for s in api('accounting'))
        print('PASS: real UDP accounting stored and visible in portal')
        # Optional full PEAP exchange using eapol_test installed in a test runner.
        eapol = os.environ.get('EAPOL_TEST')
        if eapol:
            from pathlib import Path
            config = Path('/tmp/net2net-eap-smoke.conf')
            config.write_text('network={\n key_mgmt=WPA-EAP\n eap=PEAP\n identity="' + username +
                '"\n password="' + password + '"\n phase2="auth=MSCHAPV2"\n ca_cert="/data/certs/ca.pem"\n' +
                ' domain_suffix_match="' + os.environ.get('RADIUS_SERVER_NAME', 'radius.net2net.local') + '"\n}\n')
            result = subprocess.run([eapol, '-c', str(config), '-a', '127.0.0.1', '-p', '1812', '-s', secret],
                                     capture_output=True, text=True, timeout=40)
            config.unlink(missing_ok=True)
            assert result.returncode == 0 and 'SUCCESS' in result.stdout, result.stdout + result.stderr
            print('PASS: full PEAP/MSCHAPv2 exchange with CA and server-name validation')
        body.update(status='suspended', password='')
        api('users/' + str(user_id), body, 'PUT')
        radius(username, password, secret, 'Access-Reject')
        print('PASS: suspended user rejected after config reload')
    finally:
        for collection, item_id in [('users', user_id), ('nas', nas_id), ('profiles', profile_id)]:
            if item_id is not None:
                api(collection + '/' + str(item_id), method='DELETE')
        api('logout', method='POST')
        print('Temporary users, device and VLAN profile removed')


if __name__ == '__main__':
    run()
