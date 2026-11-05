import base64
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from viewer_patch import windows_clipboard


class WindowsClipboardTests(unittest.TestCase):
    def read(self, formats, **options):
        clipboard = SimpleNamespace(
            CF_UNICODETEXT=13, CF_DIB=8,
            OpenClipboard=Mock(), CloseClipboard=Mock(),
            RegisterClipboardFormat=Mock(return_value=1000),
            IsClipboardFormatAvailable=lambda value: value in formats,
            GetClipboardData=formats.__getitem__,
        )
        with patch.dict('sys.modules', win32clipboard=clipboard):
            try:
                return windows_clipboard(**options)
            finally:
                clipboard.CloseClipboard.assert_called_once()

    def image_bytes(self, kind):
        output = io.BytesIO()
        Image.new('RGB', (2, 3), (12, 34, 56)).save(output, kind)
        return output.getvalue()

    def assert_image(self, result):
        with Image.open(io.BytesIO(base64.b64decode(result['image_png']))) as image:
            self.assertEqual(image.format, 'PNG')
            self.assertEqual(image.size, (2, 3))
            self.assertEqual(image.getpixel((0, 0)), (12, 34, 56))

    def test_existing_text_read_keeps_its_return_type(self):
        self.assertEqual(self.read({13: '中文\n🙂'}), '中文\n🙂')

    def test_png_and_text_are_read_from_one_snapshot(self):
        result = self.read({13: 'https://image.example/', 1000: self.image_bytes('PNG')}, include_image=True)
        self.assertEqual(result['text'], 'https://image.example/')
        self.assert_image(result)

    def test_windows_dib_is_converted_to_png(self):
        # CF_DIB omits the 14-byte BMP file header.
        self.assert_image(self.read({8: self.image_bytes('BMP')[14:]}, include_image=True))

    def test_plain_text_and_empty_clipboard(self):
        self.assertEqual(self.read({13: '  中文\n🙂  '}, include_image=True),
                         {'text': '  中文\n🙂  ', 'image_png': None})
        self.assertEqual(self.read({}, include_image=True), {'text': None, 'image_png': None})

    def test_invalid_image_fails_instead_of_using_its_url(self):
        with self.assertRaises(OSError):
            self.read({13: 'https://image.example/', 1000: b'broken PNG'}, include_image=True)

    def test_oversized_png_is_rejected(self):
        with patch('viewer_patch.MAX_CLIPBOARD_IMAGE_BYTES', 1), self.assertRaises(ValueError):
            self.read({1000: self.image_bytes('PNG')}, include_image=True)


if __name__ == '__main__':
    unittest.main()
