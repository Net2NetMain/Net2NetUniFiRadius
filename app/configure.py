"""Install a dedicated FreeRADIUS PEAP/MSCHAPv2 configuration and persistent PKI."""
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .main import DATA, RADIUS, initialize


def certificates():
    folder = DATA / 'certs'
    folder.mkdir(parents=True, exist_ok=True)
    expected = ['ca.pem', 'ca.key', 'server.pem', 'server.key']
    if all((folder / name).exists() for name in expected):
        return
    if any((folder / name).exists() for name in expected):
        raise RuntimeError('Incomplete certificate set. Restore all four certificate files from backup.')
    server_name = os.environ.get('RADIUS_SERVER_NAME', 'radius.net2net.local')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', server_name):
        raise RuntimeError('RADIUS_SERVER_NAME must be a DNS name')
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Net2Net UniFi RADIUS CA')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
              key_encipherment=False, data_encipherment=False, key_agreement=False,
              key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, server_name)]))
            .issuer_name(ca_name).public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(server_name)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    for name, obj in [('ca.pem', ca), ('server.pem', cert)]:
        (folder / name).write_bytes(obj.public_bytes(serialization.Encoding.PEM))
        (folder / name).chmod(0o644)
    for name, obj in [('ca.key', ca_key), ('server.key', server_key)]:
        path = folder / name
        path.write_bytes(obj.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        path.chmod(0o600)


def server_chain(folder):
    """Send the root explicitly for Android Trust on First Use enrollment."""
    path = folder / 'server-chain.pem'
    path.write_bytes((folder / 'server.pem').read_bytes().rstrip() + b'\n' +
                     (folder / 'ca.pem').read_bytes().rstrip() + b'\n')
    path.chmod(0o644)
    return path


def configure():
    initialize()
    certificates()
    root = Path(RADIUS)
    certs = DATA.resolve() / 'certs'
    server_chain(certs)
    (certs / 'ca.key').chmod(0o600)
    for name in ['ca.pem', 'server.pem']:
        (certs / name).chmod(0o644)
    shutil.chown(certs, group='freerad')
    certs.chmod(0o750)
    shutil.chown(certs / 'server.key', group='freerad')
    (certs / 'server.key').chmod(0o640)
    accounting = DATA / 'accounting'
    accounting.mkdir(exist_ok=True)
    shutil.chown(accounting, user='freerad', group='freerad')
    accounting.chmod(0o750)
    for path in (root / 'sites-enabled').iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink()
    (root / 'sites-enabled/net2net').write_text('''server default {
 listen { type = auth
  ipaddr = *
  port = 1812
 }
 listen { type = acct
  ipaddr = *
  port = 1813
 }
 authorize {
  filter_username
  preprocess
  chap
  mschap
  eap {
   ok = return
  }
  files
  pap
 }
 authenticate {
  Auth-Type PAP {
   pap
  }
  Auth-Type CHAP {
   chap
  }
  Auth-Type MS-CHAP {
   mschap
  }
  eap
 }
 preacct {
  preprocess
  acct_unique
 }
 accounting {
  detail
 }
 post-auth {
  Post-Auth-Type REJECT {
   attr_filter.access_reject
   eap
  }
 }
}
server inner-tunnel {
 authorize {
  filter_username
  mschap
  eap {
   ok = return
  }
  files
  pap
 }
 authenticate {
  Auth-Type PAP {
   pap
  }
  Auth-Type MS-CHAP {
   mschap
  }
  eap
 }
 post-auth {
  Post-Auth-Type REJECT {
   attr_filter.access_reject
  }
 }
}
''')
    (root / 'mods-available/eap').write_text(f'''eap {{
 default_eap_type = peap
 timer_expire = 60
 ignore_unknown_eap_types = no
 max_sessions = 4096
 tls-config tls-common {{
  private_key_file = {certs}/server.key
  certificate_file = {certs}/server-chain.pem
  ca_file = {certs}/ca.pem
  auto_chain = no
  tls_min_version = "1.2"
  tls_max_version = "1.2"
  cipher_list = "DEFAULT"
  ecdh_curve = "prime256v1"
  cache {{
   enable = no
  }}
 }}
 peap {{
  tls = tls-common
  default_eap_type = mschapv2
  copy_request_to_tunnel = yes
  use_tunneled_reply = yes
  virtual_server = inner-tunnel
  require_client_cert = no
 }}
 mschapv2 {{ }}
}}
''')
    (root / 'mods-available/detail').write_text(f'''detail {{
 filename = {accounting.resolve()}/%{{Packet-Src-IP-Address}}/detail-%Y%m%d
 permissions = 0600
 header = "%t"
 locking = yes
 log_packet_header = yes
}}
''')


if __name__ == '__main__':
    configure()
