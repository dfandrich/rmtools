"""Test add_matching."""

import unittest

from rmtools import add_matching


class TestIsValidUrl(unittest.TestCase):
    """Test is_valid_url."""

    def test_is_valid_url_valid(self):
        for url in [
            'https://example.com/path/file.htm',
            'ftp://something',
            'http://user@host.example:9/foo/bar/?baz&bla#f',
            'http://a/b'
        ]:
            with self.subTest(url=url):
                self.assertTrue(add_matching.is_valid_url(url))

    def test_is_valid_url_invalid(self):
        for url in [
            '//example.com/path/file.htm',
            'ftp:/path',
            '://user@host.example:9/foo/bar/?baz&bla#f',
            'file:///b',
            'http:///path'
        ]:
            with self.subTest(url=url):
                self.assertFalse(add_matching.is_valid_url(url))


class TestCanonicalize(unittest.TestCase):
    """Test canonicalize_url."""

    def test_canonicalize_url_strip(self):
        for url, canon in [
            ('https://example.com/path/file.htm', '//example.com/path/file.htm'),
            ('https://example.com/path/file.htm#ANCHOR', '//example.com/path/file.htm'),
            ('ftp://example.com/path/', '//example.com/path'),
            ('http://example.com/path/index.htm', '//example.com/path'),
            ('https://www.example.com/path', '//example.com/path'),
            ('https://sf.net/projects/xyzzy', '//sourceforge.net/projects/xyzzy'),
            ('https://sf.net/p/xyzzy', '//sourceforge.net/projects/xyzzy'),
            ('https://xyzzy.sourceforge.net/page', '//sourceforge.net/projects/xyzzy'),
            ('https://xyzzy.sf.net/page', '//sourceforge.net/projects/xyzzy'),
            ('https://download.sourceforge.net/proj', '//sourceforge.net/projects/proj'),
            ('https://download.sourceforge.net/project/xyzzy/XyZZy/1.2.3/xyzzy-1.2.3.zip',
             '//sourceforge.net/projects/xyzzy'),
            ('https://www.sourceforge.net/p/xyzzy/files/', '//sourceforge.net/projects/xyzzy'),
            ('https://xyzzy.sourceforge.io/page', '//sourceforge.net/projects/xyzzy'),
            ('https://prdownloads.sourceforge.net/proj/proj-0.12.tar.bz2',
             '//sourceforge.net/projects/proj'),
            ('https://gnu.org/s/xyzzy/more-but/ignored', '//gnu.org/software/xyzzy'),
            ('http://ftp.gnu.org/pub/gnu/xyzzy/some-file-123.tar.gz', '//gnu.org/software/xyzzy'),
            ('http://ftp.gnu.org/gnu/xyzzy/some-file-123.tar.gz', '//gnu.org/software/xyzzy'),
            ('http://alpha.gnu.org/gnu/xyzzy/some-file-123.tar.gz', '//gnu.org/software/xyzzy'),
            ('https://github.com/proj/user.git', '//github.com/proj/user'),
            ('git://github.com/proj/user.git', '//github.com/proj/user'),
            ('git+https://github.com/proj/user.foo.git', '//github.com/proj/user.foo'),
            ('https://github.com/proj/user/tarball/master', '//github.com/proj/user'),
            ('https://github.com/proj-only/', '//github.com/proj-only'),
            ('https://github.com/proj/user#readme', '//github.com/proj/user'),
            ('https://xyzzy.github.io/repo/more.htm', '//github.com/xyzzy/repo'),
            ('https://xyzzy.github.io/repo.html', '//github.com/xyzzy/repo'),
            ('https://xyzzy.github.io/', '//xyzzy.github.io'),
            ('https://rubygems.org/gems/xyzzy/versions/1.2.3', '//rubygems.org/gems/xyzzy'),
            ('https://rubygems.org/gems/xyzzy-1.2.3.gem', '//rubygems.org/gems/xyzzy'),
            ('https://rubygems.org/downloads/ok_gem-0.1.beta1.gem', '//rubygems.org/gems/ok_gem'),
            ('https://pypi.org/project/xyzzy/1.2.3', '//pypi.org/project/xyzzy'),
            ('https://pypi.python.org/pypi/xyzzy/more', '//pypi.org/project/xyzzy'),
            ('https://pypi.python.org/project/xyzzy/more', '//pypi.org/project/xyzzy'),
            ('https://pypi.python.org/pypi/dash-name', '//pypi.org/project/dash-name'),
            ('https://pypi.python.org/pypi/underscore_name', '//pypi.org/project/underscore-name'),
            ('https://pypi.python.org/packages/source/h/huggabugga/huggabugga-1.2.3.tar.gz',
             '//pypi.org/project/huggabugga'),
            ('https://pypi.io/packages/source/x/xcellent-ex/xcellent-ex-openid-3.2.1.tar.gz',
             '//pypi.org/project/xcellent-ex'),
            ('https://pypi.org/project/under_score_name', '//pypi.org/project/under-score-name'),
            ('https://files.pythonhosted.org/packages/source/u/under_score_name',
             '//pypi.org/project/under-score-name'),
            ('https://pythonhosted.org/some-project/', '//pypi.org/project/some-project'),
            ('https://search.cpan.org/dist/xyzzy', '//metacpan.org/dist/xyzzy'),
            ('https://metacpan.org/release/xyzzy', '//metacpan.org/dist/xyzzy'),
            ('https://metacpan.org/dist/xyzzy/', '//metacpan.org/dist/xyzzy'),
            ('https://releases.pagure.org/some-project/', '//pagure.io/some-project'),
            ('https://pagure.org/some-project/', '//pagure.io/some-project'),
            ('http://download.savannah.gnu.org/releases/abcd/', '//savannah.gnu.org/projects/abcd'),
            ('http://savannah.gnu.org/projects/abcd/', '//savannah.gnu.org/projects/abcd'),
            ('http://sv.gnu.org/projects/abcd/', '//savannah.gnu.org/projects/abcd'),
            ('http://savannah.gnu.org/p/abcd/', '//savannah.gnu.org/projects/abcd'),
            ('http://savannah.gnu.org/pr/abcd/', '//savannah.gnu.org/projects/abcd'),
            ('http://download.savannah.nongnu.org/releases/abcd/',
             '//savannah.nongnu.org/projects/abcd'),
            ('http://savannah.nongnu.org/projects/abcd/', '//savannah.nongnu.org/projects/abcd'),
            ('http://sv.nongnu.org/projects/abcd/', '//savannah.nongnu.org/projects/abcd'),
            ('http://savannah.nongnu.org/p/abcd/', '//savannah.nongnu.org/projects/abcd'),
            ('http://savannah.nongnu.org/pr/abcd/', '//savannah.nongnu.org/projects/abcd'),
            ('https://repo1.maven.org/maven2/org/example/top/very-cool/',
             '//central.sonatype.com/artifact/org.example.top/very-cool'),
            ('https://repo1.maven.org/maven2/org/example/plexus/plexus-component-factories/1.0-alpha-11/plexus-component-factories-1.0-alpha-11.pom',
             '//central.sonatype.com/artifact/org.example.plexus/plexus-component-factories'),
            ('https://repo1.maven.org/maven2/org/example/plexus/plexus-component-factories/maven-metadata.xml',
             '//central.sonatype.com/artifact/org.example.plexus/plexus-component-factories'),
            ('https://crates.io/crates/some-crate', '//crates.io/crates/some-crate'),
            ('https://crates.io/api/v1/crates/mycrate/0.1.2/download#/mycrate-0.1.2.crate',
             '//crates.io/crates/mycrate'),
            ('https://registry.npmjs.org/example-pkg/-/example-pkg-0.2.1.tgz',
             '//npmjs.org/package/example-pkg'),
            ('https://registry.npmjs.com/example-com/-/example-com-0.2.1.tgz',
             '//npmjs.com/package/example-com'),
            ('https://download.gnome.org/sources/the-name/1.0/the-name-1.0.7.tar.xz',
             '//download.gnome.org/sources/the-name'),
            ('ftp://ftp.gnome.org/pub/GNOME/sources/proj/proj-1.tar.bz2',
             '//download.gnome.org/sources/proj'),
            ('ftp://ftp.gnome.org/pub/gnome/sources/proj/proj-1.tar.bz2',
             '//download.gnome.org/sources/proj'),
            ('https://www.example.com/projects/xyzzy/xyzzy-1.234.5beta.tar.gz',
             '//example.com/projects/xyzzy'),
            ('https://www.example.com/z/y/x/xyzzy-1.234.5beta.tar.gz',
             '//example.com/z/y/x/xyzzy-1.234.5beta.tar.gz'),
            ('https://www.example.com/projects/xyzzy-1.2.tar.gz',
             '//example.com/projects/xyzzy-1.2.tar.gz'),
            ('ftp://example.com/pub/xyzzy/1.2/xyzzy-1.2.tar.gz',
             '//example.com/pub/xyzzy'),
            ('', ''),
        ]:
            with self.subTest(url=url, canon=canon):
                self.assertEqual(add_matching.canonicalize_url(url), canon)

    def test_canonicalize_url_nostrip(self):
        for url, canon in [
            ('https://example.com/path/file.htm', 'https://example.com/path/file.htm'),
            ('ftp://example.com/path/', 'https://example.com/path'),
            ('http://example.com/path/index.htm', 'https://example.com/path'),
            ('', ''),
        ]:
            with self.subTest(url=url, canon=canon):
                self.assertEqual(add_matching.canonicalize_url(url, strip_scheme=False), canon)


class TestMatchProjectUrl(unittest.TestCase):
    """Test match_project_url."""

    def test_match_project_url(self):
        for url1, url2 in [
            ('https://metacpan.org/dist/xyzzy/', 'https://search.cpan.org/dist/xyzzy'),
            ('https://www.github.com/Project/xyzzy/', 'http://github.com/project/xyzzy'),
        ]:
            with self.subTest(url1=url1, url2=url2):
                self.assertTrue(add_matching.match_project_url(url1, url2))

    def test_match_project_url_false(self):
        for url1, url2 in [
            ('https://example.org/dist/xyzzy/', 'https://search.cpan.org/dist/xyzzy'),
            ('https://example.com/', ''),
            ('', 'https://example.com/'),
        ]:
            with self.subTest(url1=url1, url2=url2):
                self.assertFalse(add_matching.match_project_url(url1, url2))


class TestEcosystem(unittest.TestCase):
    """Test url_ecosystem."""

    def test_url_ecosystem(self):
        for url, ecosystem in [
            ('https://metacpan.org/dist/xyzzy/', ''),
            ('https://www.github.com/Project/xyzzy/', ''),
            ('https://pypi.org/project/xyzzy/1.2.3', 'pypi'),
            ('https://npmjs.com/package/my-pkg', 'npmjs'),
            ('https://npmjs.org/package/org-pkg', 'npm'),
            ('https://crates.io/crates/some-crate', 'crates.io'),
            ('https://rubygems.org/gems/a-gem', 'rubygems'),
        ]:
            with self.subTest(url=url, ecosystem=ecosystem):
                self.assertEqual(ecosystem, add_matching.url_ecosystem(url))


class TestCompatibleEcosystems(unittest.TestCase):
    """Test compatible_ecosystems."""

    def test_compatible_ecosystems(self):
        for url1, url2 in [
            ('https://metacpan.org/dist/foobar/', 'https://search.cpan.org/dist/xyzzy'),
            ('https://www.github.com/Project/foobar/', 'https://sourceforge.net/projects/xyzzy'),
            ('https://npmjs.com/package/my-pkg', 'https://npmjs.org/package/org-pkg'),
            ('https://pypi.python.org/pypi/xyzzy', 'https://pypi.org/project/xyzzy'),
            ('http://example.com/foo', 'https://some.site.example/bar'),
        ]:
            with self.subTest(url1=url1, url2=url2):
                self.assertTrue(add_matching.compatible_ecosystems(url1, url2))

    def test_compatible_ecosystems_false(self):
        for url1, url2 in [
            ('https://crates.io/crates/some-crate', 'https://npmjs.org/package/org-pkg'),
            ('https://pypi.org/project/xyzzy', 'https://npmjs.com/package/my-pkg'),
            ('https://rubygems.org/gems/xyzzy', 'https://pypi.org/project/xyzzy'),
            ('https://rubygems.org/gems/xyzzy', ''),
            ('', 'https://example.com'),
        ]:
            with self.subTest(url1=url1, url2=url2):
                self.assertFalse(add_matching.compatible_ecosystems(url1, url2))


class TestEcosystemUrl(unittest.TestCase):
    """Test ecosystem_url."""

    def test_ecosystem_url(self):
        for ecosystem, name, url in [
            ('https://www.github.com/Project/foobar/', 'ignored',
             'https://www.github.com/Project/foobar/'),
            ('http://www.example.com/foobar/', 'ignored', 'http://www.example.com/foobar/'),
            ('ftp://weird.example.com/', 'ignored', ''),
            ('npm', 'org-pkg', 'https://npmjs.org/package/org-pkg'),
            ('npmjs', 'my-pkg', 'https://npmjs.com/package/my-pkg'),
            ('pypi', 'xyzzy', 'https://pypi.org/project/xyzzy'),
            ('crates.io', 'some-crate', 'https://crates.io/crates/some-crate'),
            ('rubygems', 'xyzzy', 'https://rubygems.org/gems/xyzzy'),
            ('other', 'xyzzy', ''),
        ]:
            with self.subTest(ecosystem=ecosystem, name=name, url=url):
                project = {'ecosystem': ecosystem, 'name': name}
                self.assertEqual(url, add_matching.ecosystem_url(project))


class TestBackendUrl(unittest.TestCase):
    """Test backend_url."""

    def test_backend_url(self):
        for backend, name, version_url, url in [
            ('GitHub', 'ignored', 'Project/foobar', 'https://github.com/Project/foobar'),
            ('GitHub', 'ignored', 'https://www.github.com/Project/foobar/',
             'https://www.github.com/Project/foobar/'),
            ('BitBucket', 'ignored', 'user/project', 'https://bitbucket.org/user/project'),
            ('Sourceforge', 'ignored', 'xyzzy', 'https://sourceforge.net/projects/xyzzy'),
            ('SourceHut', 'ignored', 'user/project', 'https://git.sr.ht/~user/project'),
            ('Maven Central', 'ignored', 'com.example.pkg:thepkg',
             'https://central.sonatype.com/artifact/com.example.pkg/thepkg'),
            ('Packagist', 'package', 'project', 'https://packagist.org/packages/project/package'),
            ('Stackage', 'ignored', None, ''),
            ('gitlab', 'ignored', 'https://gitlab.com/user/pkg', 'https://gitlab.com/user/pkg'),
            ('gitlab', 'ignored', 'ftp://could-be/anything', 'ftp://could-be/anything'),
            ('CPAN (perl)', 'ignored', '', ''),
            ('UNKNOWN', 'ignored', 'http://www.example.com/foobar/', ''),
        ]:
            with self.subTest(backend=backend, name=name, url=url):
                project = {'backend': backend, 'version_url': version_url, 'name': name}
                self.assertEqual(url, add_matching.backend_url(project))

    def test_backend_url_empty_version_url(self):
        self.assertEqual('', add_matching.backend_url({'version_url': None}))


class TestValidVersionCheckUrl(unittest.TestCase):
    """Test valid_version_check_url."""

    def test_valid_version_check_url(self):
        for url in [
            'http://example.com/dist/foobar/',
            'https://www.github.com/Project/foobar/',
            'ftp://mirror.example.com/pub/sw/',
        ]:
            with self.subTest(url=url):
                self.assertTrue(add_matching.valid_version_check_url(url))

    def test_valid_version_check_url_false(self):
        for url in [
            'justa/fragment',
            'xxxxxx',
            '',
        ]:
            with self.subTest(url=url):
                self.assertFalse(add_matching.valid_version_check_url(url))
