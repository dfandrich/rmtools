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
