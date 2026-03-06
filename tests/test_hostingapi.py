"""Test hostingapi."""

import datetime
import textwrap
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


class TestParseIso8601(unittest.TestCase):
    """Test parse_iso8601."""

    def test_parse_iso8601(self):
        for text, stamp in [
            ('2016-01-02T19:46:55Z',
             datetime.datetime(2016, 1, 2, 19, 46, 55, tzinfo=datetime.timezone.utc)),
            ('2016-01-02T19:46:55',
             datetime.datetime(2016, 1, 2, 19, 46, 55, tzinfo=datetime.timezone.utc)),
            ('2023-07-12T19:09:25.110Z',
             datetime.datetime(2023, 7, 12, 19, 9, 25, 110000, tzinfo=datetime.timezone.utc)),
            ('2025-01-19T20:28:37+01:00',
             datetime.datetime(2025, 1, 19, 20, 28, 37,
                               tzinfo=datetime.timezone(datetime.timedelta(seconds=3600))))
        ]:
            with self.subTest(text=text, stamp=stamp):
                self.assertEqual(hostingapi.parse_iso8601(text), stamp)


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


class TestGetPagureRepo(unittest.TestCase):
    """Test get_pagure_repo."""

    def test_get_pagure_repo(self):
        for repo, url in [
            ('project', 'https://pagure.io/project'),
            ('project', 'https://pagure.io/project/'),
            ('two/level', 'https://pagure.io/two/level'),
            ('rpms/rpmname', 'https://src.fedoraproject.org/rpms/rpmname/'),
            ('two/level', 'https://pagure.io/two/level/more/internal/stuff'),
            ('single', 'https://pagure.io/single/tree/master'),
            ('single', 'https://pagure.io/single/releases'),
            ('golist', 'https://pagure.io/golist/archive/v0.10.3/golist-0.10.3.tar.gz'),
            ('golist', 'https://pagure.io/golist/blob/master/f/README.md')
        ]:
            with self.subTest(repo=repo, url=url):
                self.assertEqual(hostingapi.get_pagure_repo(url), repo)

    def test_get_pagure_repo_none(self):
        for url in [
            'https://pagure.io/docs/project',
            'https://pagure.io/api/0/project',
        ]:
            with self.subTest(url=url):
                self.assertEqual(hostingapi.get_pagure_repo(url), '')


class TestParsePom(unittest.TestCase):
    """Test parse_pom."""

    def test_parse_pom(self):
        content = textwrap.dedent(r"""<?xml version='1.0' encoding='UTF-8'?>
            <project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
              <properties>
                <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
              </properties>
              <scm>
                <connection>scm:git:https://github.com/example/example.git</connection>
                <url>https://github.com/example/example/</url>
                <tag>xyzzy</tag>
              </scm>
              <licenses>
                <license>
                  <name>MIT License</name>
                  <url>http://www.opensource.org/licenses/mit-license.php</url>
                  <distribution>repo</distribution>
                </license>
              </licenses>
              <dependencies>
                <dependency>
                  <groupId>junit</groupId>
                  <artifactId>junit</artifactId>
                  <version>4.13.1</version>
                  <scope>test</scope>
                </dependency>
              </dependencies>
              <artifactId>art</artifactId>
              <version>1.2.3</version>
              <url>https://www.example.com/rmtools/v${project.version}/${project.artifactId}/${project.scm.tag}?enc=${project.build.sourceEncoding}</url>
            </project>
        """)
        self.assertCountEqual(
            hostingapi.parse_pom(content),
            ['https://github.com/example/example/',
             'https://www.example.com/rmtools/v1.2.3/art/xyzzy?enc=UTF-8'])


class TestParseSavannah(unittest.TestCase):
    """Test parse_savannah."""

    def test_parse_savannah(self):
        content = textwrap.dedent(r"""
            <html><body><div>
            <a class="foo bar tabs" href="http://invalid/">Random</a>
            <a class="foo bar tabs" href="http://more.invalid/">Other</a>
            <a class="foo bar" href="http://another.invalid/homepage">Homepage</a>
            <a class="foo bar tabs" href="http://invalid/not/real" />
            <a class="foo bar tabs" href="http://example.com/prjhome">Homepage</a>
            <a class="foo bar tabs" href="http://more2.invalid/">Final</a>
            <h2>Latest News&nbsp;</h2>
            <span class="smaller"><em>posted by <a href="/users/example">example
            </a>, Thu 11 Feb 2010 10:29:00 PM UTC</em></span>
        """)

        expected = hostingapi.ProjInfo(
            status=hostingapi.ProjInfo.ProjStatus.UNKNOWN,
            last_modified=datetime.datetime.fromtimestamp(1265927340, tz=datetime.timezone.utc),
            urls=['http://example.com/prjhome'])
        self.assertEqual(hostingapi.parse_savannah(content), expected)


class TestParseOcaml(unittest.TestCase):
    """Test parse_ocaml."""

    def test_parse_ocaml(self):
        content = textwrap.dedent(r"""
            <html><body><table>
            <tr><th>Something</th><td><a href="http://invalid/">not it</a></td></tr>
            <tr><th>Published</th><td><time datetime="2023-11-01">Nov 1, 2023</time></td></tr>
            <tr><th>Homepage</th><td><a href="http://home.example.com/">yes</a></td></tr>
            <tr><th>Source [http]</th><td><a href="http://home.example.com/code.tgz">good</a></td></tr>
            <tr><th>Garbage</th><td><a href="http://notgood.invalid/bad.tgz">bad</a></td></tr>
        """)
        expected = hostingapi.ProjInfo(
            status=hostingapi.ProjInfo.ProjStatus.UNKNOWN,
            last_modified=datetime.datetime.fromtimestamp(1698796800, tz=datetime.timezone.utc),
            urls=['http://home.example.com/', 'http://home.example.com/code.tgz'])
        self.assertEqual(hostingapi.parse_ocaml(content), expected)
