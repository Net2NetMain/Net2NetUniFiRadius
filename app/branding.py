"""Administrator-managed, raster-only portal branding stored in appliance backups."""
import base64
import binascii
import hashlib
import io
import warnings
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field
from PIL import Image, ImageOps

class LogoUpload(BaseModel):
    image: str = Field(max_length=2800000)

class BrandingText(BaseModel):
    organization_name: str = Field(max_length=100)

def register_branding(app, admin):
    from .main import db, WEB

    def image_bytes():
        with db() as c:
            row = c.execute("SELECT value FROM settings WHERE key='portal_logo'").fetchone()
        return base64.b64decode(row[0]) if row else None

    @app.get('/api/branding')
    def branding():
        data = image_bytes()
        with db() as c:
            row = c.execute("SELECT value FROM settings WHERE key='organization_name'").fetchone()
        return {'organization_name': row[0] if row else 'NET2NET NETWORK SERVICES', 'custom_logo': bool(data), 'revision': hashlib.sha256(data).hexdigest()[:16] if data else 'default'}

    @app.put('/api/branding', dependencies=[Depends(admin)])
    def update_text(body: BrandingText):
        with db() as c:
            c.execute("INSERT OR REPLACE INTO settings VALUES ('organization_name',?)", (body.organization_name.strip(),))
        return branding()

    @app.get('/api/branding/logo')
    def logo():
        data = image_bytes()
        if data is None:
            raise HTTPException(404, 'No custom logo')
        return Response(data, media_type='image/png', headers={'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff'})

    @app.get('/favicon.ico')
    def favicon():
        data = image_bytes()
        if data:
            with Image.open(io.BytesIO(data)) as source:
                icon = ImageOps.contain(source.convert('RGBA'), (64,64))
                canvas = Image.new('RGBA', (64,64)); canvas.alpha_composite(icon, ((64-icon.width)//2,(64-icon.height)//2))
                output = io.BytesIO(); canvas.save(output, format='ICO')
            return Response(output.getvalue(), media_type='image/x-icon', headers={'Cache-Control':'no-cache'})
        return Response((WEB / 'favicon.svg').read_bytes(), media_type='image/svg+xml', headers={'Cache-Control':'no-cache'})

    @app.put('/api/branding/logo', dependencies=[Depends(admin)])
    def upload(body: LogoUpload):
        try:
            raw = base64.b64decode(body.image, validate=True)
            if len(raw) > 2*1024*1024:
                raise ValueError()
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format not in ('PNG','JPEG','WEBP') or source.width*source.height > 16000000:
                        raise ValueError()
                    source.load()
                    image = ImageOps.exif_transpose(source).convert('RGBA')
                    image.thumbnail((1024,512))
                    output = io.BytesIO(); image.save(output, format='PNG')
            encoded = base64.b64encode(output.getvalue()).decode()
        except (ValueError, binascii.Error, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(422, 'Choose a valid PNG, JPG or WebP image, up to 2 MB and 16 megapixels')
        with db() as c:
            c.execute("INSERT OR REPLACE INTO settings VALUES ('portal_logo',?)", (encoded,))
        return branding()

    @app.delete('/api/branding', dependencies=[Depends(admin)])
    def reset():
        with db() as c:
            c.execute("DELETE FROM settings WHERE key='portal_logo'")
        return branding()
