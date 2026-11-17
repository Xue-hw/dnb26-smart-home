import io

from PIL import Image
import pytest

from backend.runtime import decode_image


def test_valid_jpeg_is_not_rejected_based_on_extension_or_filename():
    buffer=io.BytesIO()
    Image.new('RGB',(32,48),'white').save(buffer,format='JPEG')
    assert decode_image(buffer.getvalue()).shape==(48,32,3)


def test_pixel_limit_reports_dimensions_without_decoding_oversized_pixels(monkeypatch):
    class Header:
        format='JPEG'
        width=4896
        height=6528
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def verify(self): pytest.fail('Oversized image should be rejected before full verification/decode')
    monkeypatch.setattr(Image,'open',lambda *args:Header())
    with pytest.raises(ValueError,match='4896.*6528.*2000万'):
        decode_image(b'fixture')
