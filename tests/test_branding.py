import base64
import io
import zipfile
from PIL import Image
from test_api import client, sign_in

def test_logo_upload_persistence_backup_and_reset(client):
    assert client.get('/favicon.ico').status_code == 200
    assert client.put('/api/branding/logo',json={'image':''}).status_code == 401
    sign_in(client)
    assert client.put('/api/branding/logo',json={'image':base64.b64encode(b'<svg/>').decode()}).status_code == 422
    output=io.BytesIO();Image.new('RGB',(120,60),'red').save(output,format='PNG')
    result=client.put('/api/branding/logo',json={'image':base64.b64encode(output.getvalue()).decode()})
    assert result.status_code == 200 and result.json()['custom_logo']
    with Image.open(io.BytesIO(client.get('/api/branding/logo').content)) as image:
        assert image.size == (120,60) and image.format == 'PNG'
    assert client.get('/favicon.ico').headers['content-type'] == 'image/x-icon'
    with zipfile.ZipFile(io.BytesIO(client.get('/api/backup').content)) as archive:
        assert b'portal_logo' in archive.read('unifi.db')
    assert client.delete('/api/branding').json()['custom_logo'] is False
    assert client.get('/api/branding/logo').status_code == 404


def test_organization_name_permissions_and_persistence(client):
    assert client.get('/api/branding').json()['organization_name'] == 'NET2NET NETWORK SERVICES'
    assert client.put('/api/branding',json={'organization_name':'Example'}).status_code == 401
    sign_in(client)
    assert client.put('/api/branding',json={'organization_name':'  Example & Co  '}).json()['organization_name'] == 'Example & Co'
    assert client.get('/api/branding').json()['organization_name'] == 'Example & Co'
    assert client.delete('/api/branding').json()['organization_name'] == 'Example & Co'
    assert client.put('/api/branding',json={'organization_name':'x'*101}).status_code == 422
    assert client.put('/api/branding',json={'organization_name':''}).json()['organization_name'] == ''
