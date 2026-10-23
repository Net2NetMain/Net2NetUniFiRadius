from cryptography import x509

from app import configure


def test_complete_chain_preserves_existing_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(configure, 'DATA', tmp_path)
    configure.certificates()
    folder = tmp_path / 'certs'
    original = {p.name: p.read_bytes() for p in folder.iterdir()}
    chain = configure.server_chain(folder)
    certs = x509.load_pem_x509_certificates(chain.read_bytes())
    assert len(certs) == 2
    assert certs[0].issuer == certs[1].subject
    assert certs[1].issuer == certs[1].subject
    assert certs[1].extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    configure.certificates()
    configure.server_chain(folder)
    assert all((folder / name).read_bytes() == value for name, value in original.items())
