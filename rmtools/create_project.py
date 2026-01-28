"""Create new projects in Anitya.

Only certain URLs will work as this is tailored for certain hosting providers.
"""

import argparse
import logging
import re
import shlex
import sys
import time
from dataclasses import dataclass
from typing import Optional
from urllib import parse

from rmtools import add_matching
from rmtools import argparsing
from rmtools import external
from rmtools import find_project
from rmtools import hostingapi
from rmtools import rmapi

# Match a version string consisting entirely of numerics
NUMERIC_VER_RE = re.compile(r'^(\d+\.)*\d+$')

# Match a valid year (update this regex after 2038)
YEAR_VER_RE = re.compile(r'^((19[89])|20[0-3])\d')

# Match an alpha/beta suffix
ALPHABETA_SUFF_RE = re.compile(r'[-.]?(alpha|beta)(\.)?\d*$')
ALPHABETA_SUFF = 'alpha;beta'

# Match an rc suffix
RC_SUFF_RE = re.compile(r'[-_.]?(rc|RC)(\.)?(\d)*$')
RC_SUFF = 'rc;RC'

# Match some Python PEP440 suffixes. Not all valid versions are supported, such as .postN releases
# and developmental alpha/beta/rc releases.
PEP440_SUFF_RE = re.compile(r'(\d)(((a|b|rc)\d+)|([-._]?dev(\d+)?))$')
PEP440_SUFF = 'a;b;rc;dev'


@dataclass
class ProjectData:
    """Holds all data needed to add a new project."""
    project: str = ''
    package: str = ''
    url: str = ''
    source: str = ''
    ecosystem: str = ''


def strip_project_prefix(project_name: str, strip_prefix: list[str]):
    """Remove the first matching prefix from the name."""
    for strip in strip_prefix:
        stripped = project_name.removeprefix(strip)
        if stripped != project_name:
            project_name = stripped
            break
    return project_name


def strip_prerelease_suffix(releases: list[str]) -> str:
    """Find and remove a standard prerelease suffix in the list of release numbers.

    If one is found, it is returned and the list of releases has those prerelease suffixes removed.
    """
    # Prerelease tag checking is only needed for tag checks, not release checks, but
    # we still need it for releases to validate that the release numbers are sane.
    if any(ALPHABETA_SUFF_RE.search(r) for r in releases):
        # Strip suffix from versions
        for index, r in enumerate(releases):
            releases[index] = ALPHABETA_SUFF_RE.sub('', r)
        return ALPHABETA_SUFF

    # There is overlap between the rc and pep440 strategies, so choose the one that matches more
    rc_count = len(list(filter(None, (RC_SUFF_RE.search(r) for r in releases))))
    pep440_count = len(list(filter(None, (PEP440_SUFF_RE.search(r) for r in releases))))

    if rc_count and rc_count >= pep440_count:
        # Strip suffix from versions
        for index, r in enumerate(releases):
            releases[index] = RC_SUFF_RE.sub('', r)
        return RC_SUFF

    if rc_count and rc_count < pep440_count:
        # Strip suffix from versions
        for index, r in enumerate(releases):
            releases[index] = PEP440_SUFF_RE.sub(r'\1', r)
        return PEP440_SUFF

    return ''


def find_version_prefix(releases: list[str], extra: list[str]) -> Optional[str]:
    """Look for version prefixes that need to be removed to get a normal version number."""
    for prefix in ['', 'v', 'V', 'ver-', 'release-', 'Release-', 'ver', 'Ver', 'version-',
                   'Version-', 'v-', 'V-', 'Ver-'] + extra:
        if not any(not NUMERIC_VER_RE.search(r.removeprefix(prefix)) for r in releases):
            return prefix
    return None


class AddProject:
    """Add a project to Anitya, if known."""

    def __init__(self, rm: rmapi.RMApi, host: hostingapi.HostingAPI):
        self.rm = rm
        self.host = host

    def create_project(self, backend: str, version_url: Optional[str], prefix: str, prerelease: str,
                       release: bool, project: ProjectData):
        """Create a new project on Anitya."""
        logging.debug('Creating %s %s %s %s %s %s %s %s', project.project, project.package,
                      project.url, version_url, backend, prefix, prerelease, release)
        self.rm.create_new_project(project.project, project.url, backend, version_url, prefix,
                                   prerelease)
        # Must start a scan as a separate operation since there is no other way to set the
        # "release" flag
        self.rm.scan_project_versions(project.project, project.url, release)
        return project

    def add_project_github(self, project: ProjectData) -> Optional[ProjectData]:
        logging.info('Found GitHub URL')
        srcurl = parse.urlparse(add_matching.canonicalize_url(project.source))
        parts = srcurl.path.split('/')
        if len(parts) < 3:
            logging.warning('Bad GitHub URL %s', project.source)
            return None
        owner, repo = parts[1:]
        version_url = f'{owner}/{repo}'

        releases = self.host.get_gh_releases(project.source)
        use_release = True
        if not releases:
            use_release = False
            logging.debug('Trying tags')
            releases = self.host.get_gh_tags(project.source)
            if not releases:
                logging.warning('Skipping %s due to no tags', project.project)
                return None

        # Strip a prerelease suffix, if any
        prerelease = strip_prerelease_suffix(releases)

        # Look for prefixes that need to be removed
        prefix = find_version_prefix(releases, [project.project + '-', repo + '-'])
        if prefix is None:
            logging.warning('Skipping %s due to questionable release tags', project.project)
            logging.debug('Tags: %s', repr(releases))
            return None

        if any(YEAR_VER_RE.search(r.removeprefix(prefix)) for r in releases):
            logging.warning('Skipping %s due to possible calendar release tags', project.project)
            # TODO: set the calendar flag for these
            return None

        project.ecosystem = project.url
        return self.create_project('GitHub', version_url, prefix, prerelease, use_release, project)

    def add_project_gitlab_com(self, project: ProjectData) -> Optional[ProjectData]:
        logging.info('Found GitLab.com URL')
        srcurl = parse.urlparse(add_matching.canonicalize_url(project.source))
        parts = srcurl.path.split('/')

        # Home page link
        if len(parts) <= 2 or len(parts) == 4:
            logging.warning('Bad GitLab.com URL %s', project.source)
            return None

        # Archive link
        if len(parts) >= 5 and parts[3:5] != ['-', 'archive']:
            logging.warning('Bad GitLab.com URL %s', project.source)
            return None

        # TODO: handle three levels of namespace, not just two.
        # e.g. https://gitlab.com/kicad/libraries/kicad-symbols is a valid home page
        # with three parts.  However, it doesn't seem possible to tell based on the URL alone the
        # path to the project alone, e.g. the above is the home page to a project whereas
        # https://gitlab.com/sane-project/backends/uploads is a page within a two-part project.
        # It will probably take a round trip to the gitlab API to tell the difference.
        # Until we figure that out, only support URLs that are obviously two-part projects and
        # fail others.

        owner, repo = parts[1:3]
        version_url = add_matching.canonicalize_url(project.source, strip_scheme=False)

        # Anitya does not support gitlab.com releases yet, so there is no point in
        # looking at them for now.
        use_release = False
        logging.debug('Trying tags')
        releases = self.host.get_gitlab_com_tags(project.source)
        if not releases:
            logging.warning('Skipping %s due to no tags', project.project)
            return None

        # Strip a prerelease suffix, if any
        prerelease = strip_prerelease_suffix(releases)

        # Look for prefixes that need to be removed
        prefix = find_version_prefix(releases, [project.project + '-', repo + '-'])
        if prefix is None:
            logging.warning('Skipping %s due to questionable release tags', project.project)
            logging.debug('Tags: %s', repr(releases))
            return None

        if any(YEAR_VER_RE.search(r.removeprefix(prefix)) for r in releases):
            logging.warning('Skipping %s due to possible calendar release tags', project.project)
            # TODO: set the calendar flag for these
            return None

        project.ecosystem = project.url
        return self.create_project('GitLab', version_url, prefix, prerelease, use_release, project)

    def add_project_sourceforge(self, project: ProjectData) -> Optional[ProjectData]:
        logging.info('Found Sourceforge URL')
        srcurl = parse.urlparse(add_matching.canonicalize_url(project.source))
        parts = srcurl.path.split('/')
        if len(parts) < 3:
            logging.warning('Bad Sourceforge URL %s', project.source)
            return None
        version_url = parts[2]

        # There is no reliable API to get just the version numbers like in the GitHub API.
        # Anitya uses the RSS feed for the project and parses that, but that requires already
        # knowing the prefix and version formats. We instead just assume that the defaults are
        # sufficient, that the versions don't use Calendar format, and that Anitya's built-in
        # defaults for detecting things like RC versions are good enough.
        #
        # TODO: we should download the RSS feed and match it against the default Anitya regex
        # to at least verify that it will return something.

        project.ecosystem = project.url
        return self.create_project('Sourceforge', version_url, '', '', False, project)

    def add_project_ecosystem(self, ecosystem: str, project: ProjectData) -> Optional[ProjectData]:
        """Add this project with the correct update parameters for a number of ecosystems."""
        logging.info('Found %s URL', ecosystem)
        ecosystem_name = find_project.ecosystem_name(add_matching.canonicalize_url(project.source))
        if not ecosystem_name:
            logging.error('Skipping due to bad %s URL %s', ecosystem, project.source)
            return None
        project.ecosystem, name = ecosystem_name
        if project.project != name:
            logging.warning('Using %s ecosystem name (%s) not the supplied project name (%s)',
                            ecosystem, name, project.project)
            project.project = name

        self.create_project(ecosystem, '', '', '', False, project)
        return project

    def add_project_pypi(self, project: ProjectData) -> Optional[ProjectData]:
        return self.add_project_ecosystem('PyPI', project)

    def add_project_cratesio(self, project: ProjectData) -> Optional[ProjectData]:
        return self.add_project_ecosystem('crates.io', project)

    def add_project_rubygems(self, project: ProjectData) -> Optional[ProjectData]:
        return self.add_project_ecosystem('Rubygems', project)

    def add_project_npmjs(self, project: ProjectData) -> Optional[ProjectData]:
        return self.add_project_ecosystem('npmjs', project)

    def add_project_cpan(self, project: ProjectData) -> Optional[ProjectData]:
        """Add this project with the correct update parameters for CPAN."""
        logging.info('Found CPAN URL')
        project.ecosystem = project.url
        srcurl = parse.urlparse(add_matching.canonicalize_url(project.source))
        parts = srcurl.path.split('/')
        if len(parts) < 3 or parts[1] != 'dist':
            logging.warning('Bad CPAN URL %s', project.source)
            return None
        name = parts[2]

        if project.project != name:
            logging.warning('Using CPAN ecosystem name (%s) not the supplied project name (%s)',
                            name, project.project)
            project.project = name

        return self.create_project('CPAN (perl)', None, '', '', False, project)

    def add_project(self, project: ProjectData) -> Optional[ProjectData]:
        """Add a project to Anitya, if known.

        Only certain URLs will work as this is tailored for certain hosting providers.
        """
        logging.info('Trying to add %s', project.project)
        srcurl = parse.urlparse(add_matching.canonicalize_url(project.source))

        # Look for sources we recognize
        # TODO: sometimes the "canonical" URL is actually not and goes to a different
        # location on the site.
        if srcurl.netloc == 'pypi.org':
            return self.add_project_pypi(project)

        if srcurl.netloc == 'crates.io':
            return self.add_project_cratesio(project)

        if srcurl.netloc == 'rubygems.org':
            return self.add_project_rubygems(project)

        if srcurl.netloc in frozenset({'npmjs.org', 'npmjs.com'}):
            return self.add_project_npmjs(project)

        if srcurl.netloc == 'metacpan.org':
            return self.add_project_cpan(project)

        if srcurl.netloc == 'github.com':
            return self.add_project_github(project)

        if srcurl.netloc == 'gitlab.com':
            return self.add_project_gitlab_com(project)

        if srcurl.netloc == 'sourceforge.net':
            return self.add_project_sourceforge(project)

        logging.warning('Unsupported URL %s for %s', project.source, project.project)
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Create new projects in the Anitya database')
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
        '--dry-run',
        action='store_true',
        help='Do everything except create a project')
    parser.add_argument(
        '--distro',
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
        '--add-package',
        action=argparse.BooleanOptionalAction,
        default=True,
        help='Add the package after creating the project')
    parser.add_argument(
        '--strip-project-prefix',
        nargs='*',
        default=[],
        help='Strip one of these prefixes from the package name to create the project name')
    parser.add_argument(
        '--external-check',
        action=argparse.BooleanOptionalAction,
        default=True,
        help='Check that the URL is reachable before creating the project')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO if args.verbose else logging.WARNING,
        format='%(filename)s: %(message)s')

    if args.add_package and not args.distro:
        parser.error('--distro is required with --add-package')

    rm = rmapi.RMApi(args.token_file.read().strip(), args.dry_run)
    args.token_file.close()

    if args.gh_token_file:
        gh_token = args.gh_token_file.read().strip()
        args.gh_token_file.close()
    else:
        gh_token = None

    host = hostingapi.HostingAPI(gh_token)
    ex = external.ExternalAPI()
    ap = AddProject(rm, host)

    for l in sys.stdin:
        l = l.strip()
        try:
            lineparts = shlex.split(l)
        except ValueError:
            logging.error('Invalid format line: %s', l)
            continue
        if len(lineparts) < 3:
            logging.error('Not enough arguments in line: %s', l)
            continue
        if len(lineparts) > 4:
            logging.error('Too many arguments in line: %s', l)
            continue

        proj, pkg, url = lineparts[:3]
        src = lineparts[3] if len(lineparts) >= 4 else url

        if parse.urlparse(proj).scheme:
            logging.warning('Invalid project name (looks like URL): %s', proj)
            continue

        if parse.urlparse(pkg).scheme:
            logging.warning('Invalid package name (looks like URL): %s', pkg)
            continue

        if find_project.is_download_url(url):
            logging.error('Skipping: cannot use download URL as homepage: %s', url)
            continue

        if args.external_check:
            if not ex.check_url(url):
                logging.error('Skipping: homepage URL is not reachable: %s', url)
                continue

            if not ex.check_url(src):
                logging.warning('Source URL is not reachable (ignoring): %s', url)

        proj = strip_project_prefix(proj, args.strip_project_prefix)
        newproject = ap.add_project(ProjectData(proj, pkg, url, src))
        if newproject:
            print(' '.join(shlex.quote(r) for r in (
                newproject.project, newproject.package, newproject.url, newproject.source)))
            if args.add_package:
                rm.create_new_package(
                    args.distro, newproject.project, newproject.package, newproject.ecosystem)
        time.sleep(args.delay)


if __name__ == '__main__':
    main()
