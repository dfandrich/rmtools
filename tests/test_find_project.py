"""Test find_project."""

import unittest

from rmtools import find_project


class TestEcosystemName(unittest.TestCase):
    """Test ecosystem_name."""

    def test_ecosystem_name(self):
        for url, ecosystem_name in [
            ('https://metacpan.org/dist/xyzzy/', None),
            ('https://www.github.com/Project/xyzzy/', None),
            ('https://pypi.org/project/xyzzy/1.2.3', ('pypi', 'xyzzy')),
            ('https://npmjs.com/package/my-pkg', ('npmjs', 'my-pkg')),
            ('https://npmjs.org/package/org-pkg', ('npm', 'org-pkg')),
            ('https://crates.io/crates/some-crate', ('crates.io', 'some-crate')),
            ('https://rubygems.org/gems/a-gem', ('rubygems', 'a-gem')),
        ]:
            with self.subTest(url=url, ecosystem_name=ecosystem_name):
                self.assertEqual(ecosystem_name, find_project.ecosystem_name(url))


class TestIsDownloadUrl(unittest.TestCase):
    """Test is_download_url."""

    def test_is_download_url(self):
        for url in [
            'https://example.com/xyzzy.tar',
            'http://rubygems.invalid/foo/bar/baz.txz'
            'http://www.example.org/downloads/some_file-123.tar.gz'
            'ftp://example.com/pub/z.zip',
            'https://notmaven.org/maven2/testing.jar',
        ]:
            with self.subTest(url=url):
                self.assertTrue(find_project.is_download_url(url))

    def test_is_download_url_not(self):
        for url in [
            'https://example.com/xyzzy/',
            'http://rubygems.invalid/'
            'http://www.example.org/downloads/some_unknown-123.bin'
            'ftp://example.com/pub/unzip',
        ]:
            with self.subTest(url=url):
                self.assertFalse(find_project.is_download_url(url))


class TestSwapScheme(unittest.TestCase):
    """Test swap_scheme."""

    def test_swap_scheme(self):
        self.assertEqual('http://example.com/x', find_project.swap_scheme('https://example.com/x'))
        self.assertEqual('https://example', find_project.swap_scheme('http://example'))

    def test_swap_scheme_not(self):
        self.assertEqual('ftp://example.com/x', find_project.swap_scheme('ftp://example.com/x'))


class TestSwapWww(unittest.TestCase):
    """Test swap_www."""

    def test_swap_www(self):
        self.assertEqual('https://www.example.com/x',
                         find_project.swap_www('https://example.com/x'))
        self.assertEqual('http://www.example', find_project.swap_www('http://example'))
        self.assertEqual('ftp://www.example', find_project.swap_www('ftp://example'))

    def test_swap_www_not(self):
        self.assertEqual('http://example.com/x',
                         find_project.swap_www('http://www.example.com/x'))
        self.assertEqual('https://example', find_project.swap_www('https://www.example'))
