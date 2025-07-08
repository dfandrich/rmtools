"""Add entries that match basic checks."""

import argparse
import logging
import re
import sys
import time

from rmtools import argparsing
from rmtools import rmapi


# Match any Sourceforge home page URL
SF_HOMEPAGE_MATCH_RE = re.compile(r'^//([^/.]+)\.sourceforge\.net(/.*)?$')

# Match a github.io home page URL
GIO_HOMEPAGE_MATCH_RE = re.compile(r'^//([^/.]+)\.github\.io/([^/]+)')

# Match a PyPi homepage URL that contains a version number (probably erroneously)
PYPI_VER_STRIP_RE = re.compile(r'^(//pypi\.org/project/[^/]+)')

# Match a rubygems URL that contains a version number (probably erroneously)
RUBYGEMS_VER_STRIP_RE = re.compile(r'^(//rubygems\.org/gems/[^/]+)')

# Map Python PyPi URLs to new location
PYPIPY_MATCH_RE = re.compile(r'^//pypi\.python\.org/pypi/([^/]+)')

# Map CPAN URLs to new location
CPAN_MATCH_RE = re.compile(r'^//search\.cpan\.org/dist/([^/]+)(/)?$')

# Map MetaCPAN URLs to new location
METAREL_MATCH_RE = re.compile(r'^//metacpan\.org/release/([^/]+)(/)?$')


def canonicalize_url(url: str) -> str:
    """Canonicalize the URL, if possible, to make project URL comparison easier."""
    # TODO: perform more canonicalization:
    # - hex escaping,
    # - more alternate domain names
    url = url.rstrip('/')
    url = (url.removesuffix('/index.html').removesuffix('/index.htm').removesuffix('/index.asp')
           .removesuffix('/index.php').removesuffix('.git'))
    url = url.removeprefix('http:').removeprefix('https:')
    if url.startswith('//www.'):
        url = url.replace('//www.', '//', 1)
    if url.startswith('//sf.net/'):
        url = url.replace('//sf.net/', '//sourceforge.net/', 1)
    if url.startswith('//gnu.org/s/'):
        url = url.replace('/s/', '/software/', 1)

    # The remainder are complete and final transformations
    if r := SF_HOMEPAGE_MATCH_RE.search(url):
        return f'//sourceforge.net/projects/{r[1]}'
    if r := GIO_HOMEPAGE_MATCH_RE.search(url):
        url = f'//github.com/{r[1]}/{r[2]}'
        if url.endswith('.html'):
            return url.removesuffix('.html')
        if url.endswith('.htm'):
            return url.removesuffix('.htm')
        if url.endswith('.xhtml'):
            return url.removesuffix('.xhtml')
        return url
    if r := PYPI_VER_STRIP_RE.search(url):
        return r.group(1)
    if r := RUBYGEMS_VER_STRIP_RE.search(url):
        return r.group(1)
    if r := PYPIPY_MATCH_RE.search(url):
        return f'//pypi.org/project/{r.group(1)}'
    if r := CPAN_MATCH_RE.search(url):
        return f'//metacpan.org/dist/{r[1]}'
    if r := METAREL_MATCH_RE.search(url):
        return f'//metacpan.org/dist/{r[1]}'
    return url


def match_project_url(url1: str, url2: str) -> bool:
    """Returns True if two project URLs match after canonicalization.

    They don't necessarily have to end up at the same page, merely that they are clearly both
    pointing to the same project.
    """
    url1 = canonicalize_url(url1)
    url2 = canonicalize_url(url2)
    return url1 != '' and url1 == url2


def ecosystem_url(project: dict) -> str:
    """Returns the canonical URL for this project for its ecosystem.

    If the ecosystem doesn't support canonical URLs, return nothing.
    """
    if project['ecosystem'] == 'pypi':
        return f'https://pypi.org/project/{project["name"]}'
    if project['ecosystem'] == 'npm':
        return f'https://www.npmjs.org/package/{project["name"]}'
    if project['ecosystem'] == 'npmjs':
        return f'https://www.npmjs.com/package/{project["name"]}'
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
        if ':' in project['version_url']:
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
        return f'https://maven.apache.org/{project["version_url"].split(":")[-1]}/'
    if project['backend'] == 'Packagist':
        return f'https://packagist.org/packages/{project["version_url"]}/{project["name"]}'
    if project['backend'] in {'gitlab', 'pagure', 'Gitea', 'Cgit', 'custom'}:
        return project['version_url']
    # These backends don't have anything to offer in the version_url:
    #  CPAN (perl)
    #  CRAN (R)
    #  Debian project
    #  GNU project
    #  Hackage
    #  PECL
    #  Stackage
    return ''


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
        help='File containing token to use for authentication')
    parser.add_argument(
        '--delay',
        type=float,
        default=4,  # arbitrarily set to try to put a negligible load on the server
        help='Delay between successive entries (seconds)')
    parser.add_argument(
        '--add-remaining-packages',
        default=True,
        action='store_true',
        help='Add supplied packages even when a package is already found for the project')
    parser.add_argument(
        '--skip-existence-check',
        action='store_true',
        help='Skip the check for a package already existing in a project')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO if args.verbose else logging.WARNING,
        format='%(filename)s: %(message)s')

    # Don't support the negation
    assert args.add_remaining_packages

    rm = rmapi.RMApi(args.token_file.read().strip())
    args.token_file.close()

    # Download existing entries to use for skipping
    existing = [] if args.skip_existence_check else rm.get_distro_packages(args.distro)

    logging.info('Found %d existing packages for distro %s', len(existing), args.distro)

    # Read from input file: project, package, Homepage URL
    # TODO: fix this format because projects can contain a space (e.g. KDE Frameworks)
    # maybe allow quoting entries?
    for l in sys.stdin:
        l = l.strip()
        try:
            project, package, url = l.split(maxsplit=2)
        except ValueError:
            logging.warning('Invalid format line: %s', l)
            continue

        logging.info('Next project: %s', project)
        if package in existing:
            logging.info('Package %s already exists in a project; skipping', package)
            continue

        projects = rm.find_project(project)
        logging.debug('Found %d projects named %s', len(projects), project)
        # Find projects that match our URL
        matches = [project for project in projects
                   if (project['homepage'] and match_project_url(project['homepage'], url)
                       or (e := ecosystem_url(project)) and match_project_url(e, url)
                       or (b := backend_url(project)) and match_project_url(b, url))]
        if len(matches) == 1:
            match = matches[0]
            logging.debug('Found project %d matching ours', match['id'])
            logging.info('Adding %s to project id %d', package, match['id'])
            rm.create_new_package(args.distro, project, package, match['ecosystem'])
        else:
            if len(matches) > 1:
                logging.info('Too many matches found for our %s', project)
            elif projects:
                logging.info('No matches found for our %s', project)
            else:
                logging.info('No matches found for %s', project)

        time.sleep(args.delay)


if __name__ == '__main__':
    main()
