"""Test hostingapi."""

import unittest

from rmtools import hostingapi


class TestUnsafePath(unittest.TestCase):
    """Test unsafe_path."""

    def test_unsafe_path(self):
        for path in [
            'no/slash',
            'no#pound',
            'no:colon',
            'no[bracket]',
        ]:
            with self.subTest(path=path):
                self.assertTrue(hostingapi.unsafe_path(path))

    def test_unsafe_path_safe(self):
        for path in [
            'Just-Fine',
            'funny(ok)',
            'np_123',
            'fine!',
            'A^OK',
        ]:
            with self.subTest(path=path):
                self.assertFalse(hostingapi.unsafe_path(path))


class TestStripXmlns(unittest.TestCase):
    """Test strip_xmlns."""

    def test_strip_xmlns(self):
        for tag, stripped in [
            ('{xmlns-name}tag', 'tag'),
            ('{not-xmlns-just-funny', '{not-xmlns-just-funny'),
            ('Also{not-xmlns}', 'Also{not-xmlns}'),
            ('just-funny}tag', 'just-funny}tag'),

        ]:
            with self.subTest(tag=tag, stripped=stripped):
                self.assertEqual(hostingapi.strip_xmlns(tag), stripped)


class TestSubstituteElExpression(unittest.TestCase):
    """Test substitute_el_expression."""

    def test_substitute_el_expression(self):
        props = {
            'a': 'A',
            'bbb': 'B',
            'c': '${a}',
        }

        for text, substituted in [
            ('Nothing to substitute', 'Nothing to substitute'),
            ('First letter ${a}', 'First letter A'),
            ('${c}, ${a} ${bbb}', '${a}, A B'),
            ('Not available ${xxx} oh well', 'Not available  oh well'),
            ('Not to subst ${a', 'Not to subst ${a'),
        ]:
            with self.subTest(text=text, substituted=substituted):
                self.assertEqual(hostingapi.substitute_el_expression(text, props), substituted)


class TestExtractLink(unittest.TestCase):
    """Test extract_link."""

    def test_extract_link(self):
        for text, link in [
            ('No link at all', ''),
            ('http://full-text-is.example/link', 'http://full-text-is.example/link'),
            ('Weird links not supported <wais://example.com/link>', ''),
            ('Try an ftp link <ftp://example.com/pub/foo.lst>', 'ftp://example.com/pub/foo.lst'),
            ('Multiple http://short.example/ and https://another.example/', 'http://short.example/'),
        ]:
            with self.subTest(text=text):
                self.assertEqual(hostingapi.extract_link(text), link)


class TestGetGenericProjectName(unittest.TestCase):
    """Test _get_generic_project_name."""

    def test_get_generic_project_name(self):
        ha = hostingapi.HostingAPI(None)
        self.assertEqual(('user', 'project'),
                         ha._get_generic_project_name('https://github.com/user/project'))
        self.assertEqual(('gluser', 'glproject'),
                         ha._get_generic_project_name('https://gitlab.com/gluser/glproject'))
        self.assertEqual(('a', 'b'),
                         ha._get_generic_project_name('https://example.com/a/b'))
        # Not sure this should be accepted
        self.assertEqual(('a', 'b'),
                         ha._get_generic_project_name('not-a-url/a/b'))
        self.assertEqual(('too', 'many'),
                         ha._get_generic_project_name('https://github.com/too/many/paths'))
        self.assertEqual(('', ''),
                         ha._get_generic_project_name('https://github.com/too-few-paths'))
