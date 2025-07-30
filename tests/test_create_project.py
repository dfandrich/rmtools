"""Test create_project."""

import unittest

from rmtools import create_project


class TestRegexes(unittest.TestCase):
    """Test regular expressions."""

    def test_numeric_ver(self):
        for ver in [
            '1.2.3',
            '987',
            '20200112',
        ]:
            with self.subTest(ver=ver):
                self.assertTrue(create_project.NUMERIC_VER_RE.search(ver))

    def test_numeric_ver_false(self):
        for ver in [
            '.2.3',
            '87.',
            '5alpha2',
        ]:
            with self.subTest(ver=ver):
                self.assertFalse(create_project.NUMERIC_VER_RE.search(ver))

    def test_year_ver(self):
        for ver in [
            '19991231',
            '2020.54',
            '2038-02',
        ]:
            with self.subTest(ver=ver):
                self.assertTrue(create_project.YEAR_VER_RE.search(ver))

    def test_year_ver_false(self):
        for ver in [
            '1.2.3',
            '2222',
            '01.2026',
            '1972',
            '1901',
            '2048',
            '2099',
        ]:
            with self.subTest(ver=ver):
                self.assertFalse(create_project.YEAR_VER_RE.search(ver))

    def test_alphabeta_suff(self):
        for ver in [
            '19991231-alpha',
            '0.9beta',
            '2026.1alpha10',
            '2.beta',
        ]:
            with self.subTest(ver=ver):
                self.assertTrue(create_project.ALPHABETA_SUFF_RE.search(ver))

    def test_alphabeta_suff_false(self):
        for ver in [
            '5delta',
            '12-alpha-release',
            '5.5-bet',
        ]:
            with self.subTest(ver=ver):
                self.assertFalse(create_project.ALPHABETA_SUFF_RE.search(ver))

    def test_rc_suff(self):
        for ver in [
            '19991231-rc',
            '0.9rc5',
            '2026.1rc10',
            '2.rc',
            '0.99RC4',
        ]:
            with self.subTest(ver=ver):
                self.assertTrue(create_project.RC_SUFF_RE.search(ver))

    def test_rc_suff_false(self):
        for ver in [
            '5RCZ',
            '12-rc-release',
            '5.5-r',
        ]:
            with self.subTest(ver=ver):
                self.assertFalse(create_project.RC_SUFF_RE.search(ver))


class TestStripPrereleaseSuffix(unittest.TestCase):
    """Test strip_prerelease_suffix."""

    def test_strip_prerelease_suffix(self):
        # RC
        rel = ['v-1.2.3', 'v-99.rc1', 'v-0000.1rc', 'v-123.45_rc67']
        suffix = create_project.strip_prerelease_suffix(rel)
        self.assertEqual('rc;RC', suffix)
        self.assertEqual(['v-1.2.3', 'v-99', 'v-0000.1', 'v-123.45'], rel)

        # alpha/beta
        rel = ['1.2alpha', '1.2beta', '1.2']
        suffix = create_project.strip_prerelease_suffix(rel)
        self.assertEqual('alpha;beta', suffix)
        self.assertEqual(['1.2', '1.2', '1.2'], rel)

        # PEP440
        rel = ['v-1.2.3', 'v-99rc1', 'v-00001rc5', 'v-1b2', 'v-99.3.post12', 'v-0.dev1', 'v-1-dev2',
               'v-2dev3', 'v-3_dev4', 'v-5dev']
        suffix = create_project.strip_prerelease_suffix(rel)
        self.assertEqual('a;b;rc;dev', suffix)
        self.assertEqual(['v-1.2.3', 'v-99', 'v-00001', 'v-1', 'v-99.3.post12', 'v-0', 'v-1', 'v-2',
                          'v-3', 'v-5'], rel)


class TestFindVersionPrefix(unittest.TestCase):
    """Test find_version_prefix."""

    def test_find_version_prefix_simple(self):
        rel = ['v-1.2.3', 'v-99', 'v-0000.1']
        stripped = create_project.find_version_prefix(rel, [])
        self.assertEqual('v-', stripped)

    def test_find_version_prefix_none(self):
        rel = ['1.2.3', '99', '0000.1']
        stripped = create_project.find_version_prefix(rel, [])
        self.assertEqual('', stripped)

    def test_find_version_prefix_some(self):
        rel = ['V-1.2.3', 'V-99', '0000.1']
        stripped = create_project.find_version_prefix(rel, [])
        self.assertEqual('V-', stripped)

    def test_find_version_prefix_nomatch(self):
        rel = ['XYZ-1.2.3', 'XYZ-99', 'XYZ-0000.1']
        stripped = create_project.find_version_prefix(rel, [])
        self.assertIsNone(stripped)

    def test_find_version_prefix_extra(self):
        rel = ['XYZ-1.2.3', 'XYZ-99', 'XYZ-0000.1']
        stripped = create_project.find_version_prefix(rel, ['abc', 'XYZ-', '_'])
        self.assertEqual('XYZ-', stripped)
