"""Add entries that match basic checks."""

import argparse
import logging
import re
import shlex
import sys
import time
from typing import Optional
from urllib import parse

from rmtools import argparsing
from rmtools import hostingapi
from rmtools import rmapi


# Match scheme
MATCH_SCHEME_RE = re.compile(r'^[-+.a-zA-Z0-9]+:')

# Match a Sourceforge download page URL
SF_DOWNLOAD_MATCH_RE = re.compile(r'^//(?:download|downloads|prdownloads)\.sourceforge\.net/(?:project/)?([^/#?]+)')

# Match any Sourceforge home page URL
SF_HOMEPAGE_MATCH_RE = re.compile(r'^//([^/.]+)\.sourceforge\.(net|io)(/.*)?$')

# Match any Sourceforge home page URL
SF_SHORT_HOMEPAGE_MATCH_RE = re.compile(r'^//([^/.]+)\.sf\.net(/.*)?$')

# Match any Sourceforge project page URL
SF_MATCH_RE = re.compile(r'^(//sourceforge\.net/projects/[^/#?]+)')

# Match a github URL
GH_MATCH_RE = re.compile(r'^(//github\.com/[^/#?]+/[^/#?]+)')

# Match a github.io home page URL
GIO_HOMEPAGE_MATCH_RE = re.compile(r'^//([^/.]+)\.github\.io/([^/#?]+)')

# Map Python PyPi URLs to new location
PYPIPY_MATCH_RE = re.compile(r'^//pypi\.python\.org/(?:pypi|project)/([^/#?]+)')

# Match a PyPi homepage URL that contains a version number (probably erroneously)
PYPI_VER_STRIP_RE = re.compile(r'^(//pypi\.org/project/[^/#?]+)')

# Match a pythonhosted download link to its PyPi homepage URL
PYTHONHOSTED_MATCH_RE = re.compile(r'//(?:files\.pythonhosted\.org|pypi\.python\.org|pypi\.io)/packages/source/./([^/#?]+)')

# Match a pythonhosted home page link to its PyPi homepage URL
PYTHONHOSTED_HOME_MATCH_RE = re.compile(r'//pythonhosted\.org/([^/#?]+)')

# Match a rubygems URL that contains a version number (probably erroneously)
RUBYGEMS_VER_STRIP_RE = re.compile(r'^(//rubygems\.org/gems/[^/#?]+)')

# Map CPAN URLs to new location
CPAN_MATCH_RE = re.compile(r'^//search\.cpan\.org/dist/([^/#?]+)(/)?$')

# Map MetaCPAN URLs to new location
METAREL_MATCH_RE = re.compile(r'^//metacpan\.org/release/([^/#?]+)(/)?$')

# Map Pagure release URLs to main page
PAGURE_RELEASE_MATCH_RE = re.compile(r'^//releases\.pagure\.org/([^/#?]+)')

# Map Pagure release URLs to new URL
PAGUREORG_MATCH_RE = re.compile(r'^//pagure\.org/([^/#?]+)')

# Match any GNU project page URL
GNU_MATCH_RE = re.compile(r'^//gnu\.org/software/([^/#?]+)')

# Match any GNU download page URL
GNUFTP_MATCH_RE = re.compile(r'^//(?:ftp|alpha)\.gnu\.org/(?:pub/)?gnu/([^/#?]+)')

# Match any GNU Savannah project page URL
GNUSAV_MATCH_RE = re.compile(r'^//(?:savannah|sv)\.gnu\.org/p(?:r(?:ojects)?)?/([^/#?]+)')

# Match any GNU Savannah download page URL
GNUSAVDL_MATCH_RE = re.compile(r'^//download\.savannah\.gnu\.org/releases/([^/#?]+)')

# Match any Non-GNU Savannah project page URL
NONGNUSAV_MATCH_RE = re.compile(r'^//(?:savannah|sv)\.nongnu\.org/p(?:r(?:ojects)?)?/([^/#?]+)')

# Match any Non-GNU Savannah download page URL
NONGNUSAVDL_MATCH_RE = re.compile(r'^//download\.savannah\.nongnu\.org/releases/([^/#?]+)')

# Match a Gnome download page URL
GNOME_DOWNLOAD_MATCH_RE = re.compile(r'^//download\.gnome\.org/sources/([^/#?]+)')

# Match the Gnome FTP download page URL
GNOME_FTPDOWNLOAD_MATCH_RE = re.compile(r'^//ftp\.gnome\.org/pub/(?:GNOME|gnome)/sources/([^/#?]+)')

# Match the npmjs download page URL
NPMJSREG_MATCH_RE = re.compile(r'^//registry\.(npmjs\.(?:org|com))/([^/#?]+)')

# Match the maven download page URL (try to match this first)
MAVENDL_MATCH_RE = re.compile(r'^//repo1\.maven\.org/maven2/(.+)/([^/]+)/((maven-metadata\.xml)|(\d[-.\w]+/[^/]+\.(zip|jar|tar\..z|pom)))$')

# Match the maven download page root URL
MAVEN_MATCH_RE = re.compile(r'^//repo1\.maven\.org/maven2/(.+)/([^/]+)(/)?$')

# Match a download archive link that repeats the project name in the download URL
DOWNLOAD_ARCHIVE_STRIP_RE = re.compile(r'^(//.*/([^/]{3,}))/([0-9.]+/)?\2-\d[\w.]*\.(tar|zip|lzh|rar|cab|tgz|tbz|txz|jar)(\.\w{1,5})?$')

# Ecosystems that correspond to certain canonical URL hosts
ECOSYSTEM_HOSTS = {
    'pypi.org': 'pypi',
    'npmjs.org': 'npm',
    'npmjs.com': 'npmjs',
    'crates.io': 'crates.io',
    'rubygems.org': 'rubygems',
}

# Ecosystems that can't possible point to the same package WITH SOME EXCEPTIONS
MUTUALLY_INCOMPATIBLE_ECOSYSTEMS = {'pypi', 'npm', 'npmjs', 'crates.io', 'rubygems', 'maven'}


def is_valid_url(url: str) -> bool:
    """Checks whether the given URL is a valid, absolute one that might be retrieved."""
    scheme, netloc, _, _, _, _ = parse.urlparse(url)
    return scheme.lower() in frozenset({'http', 'https', 'ftp', 'ftps'}) and netloc != ''


def canonicalize_url(url: str, strip_scheme: bool = True) -> str:
    """Canonicalize the URL, if possible, to make project URL comparison easier.

    Anything unneeded to disambiguate the project is eliminated.

    Args:
        url: URL to canonicalize
        strip_scheme: The returned URL has no scheme if True, scheme is https: otherwise
    """
    # TODO: perform more canonicalization:
    # - hex escaping,
    # - more alternative domain names
    # - scheme & hostname case lowering
    # - maybe map metacpan.org/module/Search::Xapian to metacpan.org/dist/Search-Xapian
    # - X.gitlab.io/Y
    # https://central.sonatype.org/ == https://search.maven.org/
    url = url.rstrip('/')
    url = (url.removesuffix('/index.html').removesuffix('/index.htm').removesuffix('/index.asp')
           .removesuffix('/index.php').removesuffix('/index.jsp').removesuffix('.git'))
    url = MATCH_SCHEME_RE.sub('', url)
    if url.startswith('//www.'):
        url = url.replace('//www.', '//', 1)
    if url.startswith('//sf.net/'):
        url = url.replace('//sf.net/', '//sourceforge.net/', 1)
    if url.startswith('//sourceforge.net/p/'):
        url = url.replace('//sourceforge.net/p/', '//sourceforge.net/projects/', 1)
    if url.startswith('//gnu.org/s/'):
        url = url.replace('/s/', '/software/', 1)
    if '#' in url:
        url = url[:url.index('#')]

    scheme = '' if strip_scheme or not url.startswith('/') else 'https:'

    # The remainder are complete and final transformations
    if ((r := SF_DOWNLOAD_MATCH_RE.search(url)) or (r := SF_HOMEPAGE_MATCH_RE.search(url))
            or (r := SF_SHORT_HOMEPAGE_MATCH_RE.search(url))):
        return scheme + f'//sourceforge.net/projects/{r[1]}'
    if r := SF_MATCH_RE.search(url):
        return scheme + r.group(1)
    if r := GH_MATCH_RE.search(url):
        return scheme + r.group(1)
    if r := GIO_HOMEPAGE_MATCH_RE.search(url):
        url = f'//github.com/{r[1]}/{r[2]}'
        if url.endswith('.html'):
            return scheme + url.removesuffix('.html')
        if url.endswith('.htm'):
            return scheme + url.removesuffix('.htm')
        if url.endswith('.xhtml'):
            return scheme + url.removesuffix('.xhtml')
        return scheme + url
    if ((r := PYPIPY_MATCH_RE.search(url)) or (r := PYTHONHOSTED_MATCH_RE.search(url))
            or (r := PYTHONHOSTED_HOME_MATCH_RE.search(url))):
        module = r.group(1).replace('_', '-')
        return scheme + f'//pypi.org/project/{module}'
    if r := PYPI_VER_STRIP_RE.search(url):
        return scheme + r.group(1).replace('_', '-')
    if r := RUBYGEMS_VER_STRIP_RE.search(url):
        return scheme + r.group(1)
    if r := CPAN_MATCH_RE.search(url):
        return scheme + f'//metacpan.org/dist/{r[1]}'
    if r := METAREL_MATCH_RE.search(url):
        return scheme + f'//metacpan.org/dist/{r[1]}'
    if (r := PAGURE_RELEASE_MATCH_RE.search(url)) or (r := PAGUREORG_MATCH_RE.search(url)):
        return scheme + f'//pagure.io/{r[1]}'
    if (r := GNU_MATCH_RE.search(url)) or (r := GNUFTP_MATCH_RE.search(url)):
        return scheme + f'//gnu.org/software/{r[1]}'
    if (r := GNUSAV_MATCH_RE.search(url)) or (r := GNUSAVDL_MATCH_RE.search(url)):
        return scheme + f'//savannah.gnu.org/projects/{r[1]}'
    if (r := NONGNUSAV_MATCH_RE.search(url)) or (r := NONGNUSAVDL_MATCH_RE.search(url)):
        return scheme + f'//savannah.nongnu.org/projects/{r[1]}'
    if (r := GNOME_DOWNLOAD_MATCH_RE.search(url)) or (r := GNOME_FTPDOWNLOAD_MATCH_RE.search(url)):
        return scheme + f'//download.gnome.org/sources/{r[1]}'
    if r := NPMJSREG_MATCH_RE.search(url):
        return scheme + f'//{r[1]}/package/{r[2]}'
    if (r := MAVENDL_MATCH_RE.search(url)) or (r := MAVEN_MATCH_RE.search(url)):
        group = '.'.join(r.group(1).split('/'))
        artifact = r.group(2)
        return scheme + f'//central.sonatype.com/artifact/{group}/{artifact}'

    # This is a generic match that should be last
    if r := DOWNLOAD_ARCHIVE_STRIP_RE.search(url):
        return scheme + r.group(1)
    return scheme + url if url else ''


def valid_version_check_url(url: str) -> str:
    """Validate that the given Anitya version check URL looks like a URL.

    In the case of a non-URLs, an empty string is returned. This is necessary because for some
    ecosystems, only a URL fragment is available and not a full URL (such URLs are expanded
    by ecosystem_url()).
    """
    scheme, netloc, _, _, _ = parse.urlsplit(url)
    if not netloc or not scheme or scheme.lower() not in frozenset({'http', 'https', 'ftp', 'ftps'}):
        return ''
    return url


def match_project_url(url1: str, url2: str) -> bool:
    """Returns True if two project URLs match after canonicalization.

    They don't necessarily have to end up at the same page, merely that they are clearly both
    pointing to the same project.
    """
    if not url1 or not url2:
        # They can not match if one is blank
        return False
    url1 = canonicalize_url(url1)
    url2 = canonicalize_url(url2)
    return url1 != '' and url1.lower() == url2.lower()


def url_ecosystem(url: str) -> str:
    """Returns the ecosystem of the given canonicalized package URL.

    These ecosystems don't necessarily map exactly the same way as Anity's do. In particular, an
    unrecognized URL returns an empty string instead of the URL itself.
    """
    _, netloc, _, _, _ = parse.urlsplit(url)
    return ECOSYSTEM_HOSTS.get(netloc, '')


def compatible_ecosystems(url1: str, url2: str) -> bool:
    """Compares ecosystems of canonical URLs and returns whether they could possibly match.

    Some ecosystems are specific to a single language, so two projects, each in a different one
    of those ecosystems, could never actually be the same project. This sanity check can be used
    as an optimization to eliminate unnecessary work in comparing projects. For example, a Python
    package will never use a Rust ecosystem as its URL.
    """
    if not url1 or not url2:
        # They can not match if one is blank
        return False
    eco1 = url_ecosystem(url1)
    eco2 = url_ecosystem(url2)
    logging.debug('Ecosystems %s and %s', eco1, eco2)
    if eco1 == eco2:
        # The same ecosystem is compatible with itself, even if both are empty
        return True

    # An exception to the mutually incompatible ecosystems set
    if eco1 in {'npm', 'npmjs'} and eco2 in {'npm', 'npmjs'}:
        return True

    # At least one of them needs to be in a generic ecosystem for a chance at compatibility
    return (eco1 not in MUTUALLY_INCOMPATIBLE_ECOSYSTEMS
            or eco2 not in MUTUALLY_INCOMPATIBLE_ECOSYSTEMS)


def ecosystem_url(project: dict) -> str:
    """Returns the canonical URL for this project for its ecosystem.

    If the ecosystem doesn't support canonical URLs, return nothing.
    """
    if project['ecosystem'] == 'pypi':
        return f'https://pypi.org/project/{project["name"]}'
    if project['ecosystem'] == 'npm':
        return f'https://npmjs.org/package/{project["name"]}'
    if project['ecosystem'] == 'npmjs':
        return f'https://npmjs.com/package/{project["name"]}'
    if project['ecosystem'] == 'crates.io':
        return f'https://crates.io/crates/{project["name"]}'
    if project['ecosystem'] == 'rubygems':
        return f'https://rubygems.org/gems/{project["name"]}'
    if project['ecosystem'].startswith('https://') or project['ecosystem'].startswith('http://'):
        return project['ecosystem']  # Looks like a full URL
    # Not sure what to do with the 'maven' ecosystem; the URL doesn't always have the name in it
    return ''


def backend_url(project: dict) -> str:
    """Returns the canonical URL for this project for its backend.

    If the backend doesn't support canonical URLs, return nothing.
    """
    if not project['version_url']:
        return ''
    if project['backend'] == 'GitHub':
        if MATCH_SCHEME_RE.search(project['version_url']):
            # This is erroneously containing the entire URL, not just the project/name
            return project['version_url']
        return f'https://github.com/{project["version_url"]}'
    if project['backend'] == 'BitBucket':
        return f'https://bitbucket.org/{project["version_url"]}'
    if project['backend'] == 'Sourceforge':
        return f'https://sourceforge.net/projects/{project["version_url"]}'
    if project['backend'] == 'SourceHut':
        return f'https://git.sr.ht/~{project["version_url"]}'
    if project['backend'] == 'Maven Central':
        return f'https://central.sonatype.com/artifact/{project["version_url"].replace(":", "/")}'
    if project['backend'] == 'Packagist':
        return f'https://packagist.org/packages/{project["version_url"]}/{project["name"]}'
    if project['backend'] in {'gitlab', 'pagure', 'Gitea', 'Cgit', 'custom'}:
        return project['version_url']
    # These backends don't have anything new to offer in the version_url:
    #  CPAN (perl)
    #  CRAN (R)
    #  Debian project
    #  GNU project
    #  Hackage
    #  PECL
    #  Stackage
    return ''


class ExternalComparer:
    """Class to handle comparing projects using external resources."""

    def __init__(self, gh_token: Optional[str]):
        self.hostapi = hostingapi.HostingAPI(gh_token)

    def compare(self, url: str, projects: list[dict]) -> list[dict]:
        """Compare projects by visiting external sites to gather information.

        Returns:
            list of projects that match enough of our criteria to be considered matched
        """
        canon_url = canonicalize_url(url, strip_scheme=False)
        for proj in projects:
            eco_url = canonicalize_url(ecosystem_url(proj), strip_scheme=False)
            be_url = canonicalize_url(backend_url(proj), strip_scheme=False)
            logging.debug('Ecosystem compare %s with %s & %s',
                          canon_url, eco_url, be_url)
            if (compatible_ecosystems(canon_url, eco_url)
                    or compatible_ecosystems(canon_url, be_url)):
                break
        else:
            logging.info('Skipping external match check due to incompatible ecosystems')
            return []

        if (url_ecosystem(canon_url)
                and all(url_ecosystem(backend_url(proj)) for proj in projects)
                and all(url_ecosystem(ecosystem_url(proj)) for proj in projects)):
            logging.error('External matching not yet implemented for any url available')
            return []

        exturls = self.hostapi.get_project_links(canon_url)
        if exturls:
            logging.debug('Found external project links %s', ' '.join(exturls))
        else:
            logging.debug('No external project links found for %s', canon_url)

        def check_all_links(check_url: str):
            """Check the given URL against all relevant ones."""
            # First, check the URL directly against the main URL
            if match_project_url(check_url, url):
                return True

            # Next, check the URL against project links of the main URL
            for link in exturls:
                if match_project_url(check_url, link):
                    return True

            # Now, get project links for the URL and check those against the main
            proj_urls = self.hostapi.get_project_links(canonicalize_url(check_url))
            logging.debug('Proj links %s', ' '.join(proj_urls))
            for proj_url in proj_urls:
                if match_project_url(proj_url, url):
                    return True
                # Finally, check the project links against project links of the main URL
                for link in exturls:
                    if match_project_url(proj_url, link):
                        return True
            return False

        matches = []
        for proj in projects:
            logging.debug('Matching project %s (%s) against %s %s',
                          proj['name'], proj['id'], url, ' '.join(exturls))

            if (check_all_links(proj['homepage'])
                or check_all_links(ecosystem_url(proj))
                    or check_all_links(backend_url(proj))):
                matches.append(proj)

        # dicts aren't hashable so we can't just dump them into a set to deduplicate them,
        # so do it manually instead.
        unique_ids = set({})
        unique = []
        for proj in matches:
            if proj['id'] not in unique_ids:
                unique.append(proj)
                unique_ids.add(proj['id'])
        return unique
        # TODO:
        # - check URLs for HTTP redirects
        # - retrieve more Project/Homepage
        # - retrieve Project/Download links, if appropriate


def main():
    parser = argparse.ArgumentParser(
        description='Add entries to the Anitya database')
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Enable verbose logging')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging')
    parser.add_argument(
        '--distro',
        required=True,
        help='Distro name to use for added entries')
    parser.add_argument(
        '--token-file',
        required=True,
        type=argparsing.ExpandUserFileName('r'),
        help='File containing Anitya token to use for authentication')
    parser.add_argument(
        '--gh-token-file',
        type=argparsing.ExpandUserFileName('r'),
        help='File containing GitHub token to use for authentication')
    parser.add_argument(
        '--delay',
        type=float,
        default=4,  # arbitrarily set to try to put a negligible load on the server
        help='Delay between successive entries (seconds)')
    parser.add_argument(
        '--dump-existing',
        type=argparsing.ExpandUserFileName('w'),
        help='File in which to write packages existing in Anitya')
    parser.add_argument(
        '--existence-check',
        action=argparse.BooleanOptionalAction,
        default=True,
        help='Check for a package already existing in a project by downloading the complete list')
    parser.add_argument(
        '--external-match',
        action=argparse.BooleanOptionalAction,
        default=True,
        help='Look harder for matching projects by contacting other servers')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO if args.verbose else logging.WARNING,
        format='%(filename)s: %(message)s')

    rm = rmapi.RMApi(args.token_file.read().strip())
    args.token_file.close()

    if args.gh_token_file:
        gh_token = args.gh_token_file.read().strip()
        args.gh_token_file.close()
    else:
        gh_token = None

    # Download existing entries to use for skipping
    existing = rm.get_distro_packages(args.distro) if args.existence_check else set()

    logging.info('Found %d existing packages for distro %s', len(existing), args.distro)

    external = ExternalComparer(gh_token)

    # Read from input file: project, package, Homepage URL, another URL
    # Arguments can be quoted to embed spaces
    for l in sys.stdin:
        l = l.strip()
        try:
            lineparts = shlex.split(l)
        except ValueError:
            logging.warning('Invalid format line: %s', l)
            continue
        if len(lineparts) < 3:
            logging.warning('Not enough arguments in line: %s', l)
            continue
        if len(lineparts) > 4:
            logging.warning('Too many arguments in line: %s', l)
            continue
        project, package = lineparts[:2]
        urls = lineparts[2:]

        logging.info('Next project: %s', project)
        if package in existing:
            logging.info('Package %s already exists in a project; skipping', package)
            continue

        urls = [url for url in urls if is_valid_url(url)]
        if not urls:
            logging.info('No valid URLs given; skipping')
            continue

        projects = rm.find_project(project)
        logging.debug('Found %d projects named %s', len(projects), project)
        # Find projects that match our URL
        for proj in projects:
            logging.debug('Anitya links %s %s %s %s',
                          proj['homepage'], valid_version_check_url(proj['version_url']),
                          ecosystem_url(proj), backend_url(proj))
        matches = [proj for proj in projects
                   for url in urls
                   if (match_project_url(proj['homepage'], url)
                       or match_project_url(valid_version_check_url(proj['version_url']), url)
                       or match_project_url(ecosystem_url(proj), url)
                       or match_project_url(backend_url(proj), url))]

        if not matches and projects and args.external_match:
            # No matches, but there were projects found.
            # Do an extended comparison to try harder to find a match.
            for url in urls:
                matches.extend(external.compare(url, projects))

        # Dedupe matches, since more than one input URL could match
        matchset = frozenset(proj['id'] for proj in matches)
        if len(matchset) == 1:
            # One good match
            match = matches[0]
            logging.debug('Found project %d matching ours', match['id'])
            logging.info('Adding %s to project id %d', package, match['id'])
            rm.create_new_package(args.distro, project, package, match['ecosystem'])
            print(package)
            existing.add(package)

        elif len(matchset) > 1:
            logging.info('Too many matches found for our %s', project)

        elif projects:
            logging.info('No matches found for our %s', project)

        else:
            logging.info('No matches found for %s', project)

        time.sleep(args.delay)

    if args.dump_existing:
        with args.dump_existing as f:
            pkgs = list(existing)
            pkgs.sort()
            f.write('\n'.join(package for package in pkgs))
            f.write('\n')


if __name__ == '__main__':
    main()
