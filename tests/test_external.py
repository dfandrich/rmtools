"""Test external."""

import unittest

from rmtools import external


class TestParseRefreshUrl(unittest.TestCase):
    """Test parse_refresh_url."""

    def test_parse_refresh_url(self):
        for content, url in [
                ('0; url=https://example.com/xyz', 'https://example.com/xyz'),
                ('1; url=/path', '/path'),
                (' 0 ;  url = https://example.com/XYZ  ', 'https://example.com/XYZ'),
                ('123;url=ftp://x.example', 'ftp://x.example'),
                ('99;\turl\t=\thttp://x.example', 'http://x.example'),
                (';url=http://x', ''),
                (';http://x', ''),
                ('http://x', ''),
        ]:
            with self.subTest(content=content, url=url):
                self.assertEqual(url, external.parse_refresh_url(content))
