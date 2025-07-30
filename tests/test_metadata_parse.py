"""Test metadata_parse."""

import unittest

from rmtools import metadata_parse


class TestRegexes(unittest.TestCase):
    """Test regular expressions."""

    def test_package_re(self):
        for pkg, name in [
            ('package-name-with-dashes-9.1-1.1.abc9.src.rpm', 'package-name-with-dashes'),
            ('rubygem-xyzzy-1.7.0-13.zy43.src.rpm', 'rubygem-xyzzy'),
            ('a-b-c-0.2-0.git20200506.5.abc9.src.rpm', 'a-b-c'),
            ('lib345-1.3.0-22.mga9.src.rpm', 'lib345'),
        ]:
            with self.subTest(pkg=pkg, name=name):
                self.assertEqual(name, metadata_parse.PACKAGE_RE.search(pkg).group(1))


class TestStripPrefixes(unittest.TestCase):
    """Test strip_prefixes."""

    def test_strip_prefixes(self):
        prefixes = ['a-', 'b', 'CCC']
        for name, stripped in [
            ('nothing', 'nothing'),
            ('a-bcd', 'bcd'),
            ('bcd', 'cd'),
            ('bb', 'b'),
            ('CCC', ''),
            ('CCC_', '_'),
            ('a-bCCCdone', 'bCCCdone'),
        ]:
            with self.subTest(name=name, stripped=stripped):
                self.assertEqual(stripped, metadata_parse.strip_prefixes(name, prefixes))
