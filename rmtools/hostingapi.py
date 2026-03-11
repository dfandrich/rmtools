"""API to access external code hosting providers."""

import contextlib
import datetime
import enum
import functools
import html.parser
import json
import locale
import logging
import re
import sys
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from urllib import parse

from rmtools import netreq

JSON_DATA_TYPE = 'application/json'
XML_DATA_TYPE = 'application/xml'
HTML_DATA_TYPE = 'text/html'

# See https://docs.github.com/en/rest?apiVersion=2022-11-28
GH_API_URL = 'https://api.github.com'
GH_BASE_URL = GH_API_URL + '/repos/{owner}/{repo}'
GH_RELEASES_URL = GH_BASE_URL + '/releases'
GH_TAGS_URL = GH_BASE_URL + '/tags'
GH_API_VERSION = '2022-11-28'
GH_DATA_TYPE = 'application/vnd.github+json'

# See https://wiki.python.org/moin/PyPIJSON
PYPI_API_URL = 'https://pypi.org/pypi'
PYPI_BASE_URL = PYPI_API_URL + '/{project}/json'

CRATES_API_URL = 'https://crates.io/api/v1'
CRATES_BASE_URL = CRATES_API_URL + '/crates/{crate}'

CPAN_API_URL = 'https://fastapi.metacpan.org/v1'
CPAN_BASE_URL = CPAN_API_URL + '/release/{module}'

# See https://sourceforge.net/api-docs/
SF_API_URL = 'https://sourceforge.net/rest'
SF_BASE_URL = SF_API_URL + '/p/{project}'
SF_ACTIVITY_URL = SF_BASE_URL + '/activity'

NPM_API_URL = 'https://registry.npmjs.org'
NPM_BASE_URL = NPM_API_URL + '/{package}'

NPMJS_API_URL = 'https://registry.npmjs.com'
NPMJS_BASE_URL = NPMJS_API_URL + '/{package}'

RUBY_API_URL = 'https://rubygems.org/api/v1'
RUBY_BASE_URL = RUBY_API_URL + '/gems/{gem}.json'

MAVEN_API_URL = 'https://repo1.maven.org/maven2'
MAVEN_BASE_URL = MAVEN_API_URL + '/{group_hier}/{artifact}/maven-metadata.xml'
MAVEN_POM_URL = MAVEN_API_URL + '/{group_hier}/{artifact}/{version}/{artifact}-{version}.pom'
MAVEN_SEARCH_BASE_URL = 'https://search.maven.org/solrsearch'
MAVEN_SEARCH_URL = MAVEN_SEARCH_BASE_URL + '/select?q=g:{group}%20AND%20a:{artifact}&rows=9&wt=json'
MAVEN_USE_SEARCH = True

# See https://docs.gitlab.com/api/rest/
GITLAB_API_URL = 'https://gitlab.com/api/v4'
GITLAB_BASE_URL = GITLAB_API_URL + '/projects/{namespace}%2F{project}'
GITLAB_COM_PAGES_URL = 'https://{namespace}.gitlab.io/{project}'
GITLAB_TAGS_URL = GITLAB_BASE_URL + '/repository/tags'
GITLAB_INACTIVE_URL = GITLAB_API_URL + '/projects?search={namespace}+{project}&simple=true&active=false'

# Note this is a two-stage template: first state is to replace the domain only
PRIVATE_GITLAB_API_URL = 'https://{domain}/api/v4'
PRIVATE_GITLAB_BASE_URL = PRIVATE_GITLAB_API_URL + '/projects/{{namespace}}%2F{{project}}'
# Note this is a two-stage template: first state is to replace the domain only
PRIVATE_GITLAB_PAGES_URL = 'https://{{namespace}}.pages.{domain}/{{project}}'
# Note this is a two-stage template: first state is to replace the domain only
# This URL is not reliable, since private instances can move archived projects so the namespace
# no longer matches (e.g. gitlab.gnome.org moves them to "Archive")
PRIVATE_GITLAB_INACTIVE_URL = PRIVATE_GITLAB_API_URL + '/projects?search={{namespace}}+{{project}}&simple=true&active=false'

# See https://codeberg.org/api/swagger
CODEBERG_API_URL = 'https://codeberg.org/api/v1'
CODEBERG_BASE_URL = CODEBERG_API_URL + '/repos/{owner}/{repo}'
CODEBERG_RELEASES_URL = CODEBERG_BASE_URL + '/releases'
CODEBERG_TAGS_URL = CODEBERG_BASE_URL + '/tags'
CODEBERG_PAGES_URL = 'https://{owner}.codeberg.page/{repo}'

FEDORAFORGE_API_URL = 'https://forge.fedoraproject.org/api/v1'
FEDORAFORGE_BASE_URL = FEDORAFORGE_API_URL + '/repos/{owner}/{repo}'
FEDORAFORGE_RELEASES_URL = FEDORAFORGE_BASE_URL + '/releases'
FEDORAFORGE_TAGS_URL = FEDORAFORGE_BASE_URL + '/tags'
# There doesn't seem to be a pages URL for projects hosted here

# See https://pagure.io/api/0/
PAGUREIO_API_URL = 'https://pagure.io/api/0'
PAGUREIO_BASE_URL = PAGUREIO_API_URL + '/{repo}'
PAGUREIO_TAGS_URL = PAGUREIO_BASE_URL + '/git/tags'

SRCFEDORA_API_URL = 'https://src.fedoraproject.org/api/0'
SRCFEDORA_BASE_URL = SRCFEDORA_API_URL + '/{repo}'
SRCFEDORA_TAGS_URL = SRCFEDORA_BASE_URL + '/git/tags'

# See https://api.launchpad.net/devel.html
LAUNCHPAD_API_URL = 'https://launchpad.net/api/devel/'
LAUNCHPAD_BASE_URL = LAUNCHPAD_API_URL + '{project}'
LAUNCHPAD_OP_URL = LAUNCHPAD_BASE_URL + '?ws.op={op}{extra}'

GNUSV_API_URL = 'https://savannah.gnu.org'
GNUSV_BASE_URL = GNUSV_API_URL + '/projects/{project}'

NONGNUSV_API_URL = 'https://savannah.nongnu.org'
NONGNUSV_BASE_URL = NONGNUSV_API_URL + '/projects/{project}'

OPAM_API_URL = 'https://opam.ocaml.org/packages'
OPAM_BASE_URL = OPAM_API_URL + '/{package}/'

READTHEDOCS_API_URL = 'https://app.readthedocs.org/api/v3/'
READTHEDOCS_BASE_URL = READTHEDOCS_API_URL + '/projects/{project}/'

GOOGLECODE_API_URL = 'https://storage.googleapis.com/storage/v1/b/google-code-archive/o/v2%2Fcode.google.com%2F'
GOOGLECODE_BASE_URL = GOOGLECODE_API_URL + '{project}%2Fproject.json'
GOOGLECODE_INFO_URL = GOOGLECODE_BASE_URL + '?alt=media&stripTrailingSlashes=false'

# Characters that are safe in URLs without special handling
SAFE_CHARS_RE = re.compile(r'^[-a-zA-Z0-9()._!^]*$')

# EL expression parser
EL_EXPRESSION_RE = re.compile(r'\${([^}]*)}')

# RE to find a link in plain text
TEXT_LINK_RE = re.compile(r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])')

# Thread lock for switching locales
LOCALE_LOCK = threading.Lock()


@dataclass
class ProjInfo:
    """Information about a hosted project."""

    class ProjStatus(enum.IntEnum):
        """Project status conditions."""
        UNKNOWN = enum.auto()   # unable to determine project status
        INVALID = enum.auto()   # project existed but is no longer available (disabled)
        VALID = enum.auto()     # project exists and is enabled

    status: ProjStatus
    last_modified: Optional[datetime.datetime]
    urls: list[str]


def parse_iso8601(stamp: str) -> datetime.datetime:
    """Parse an ISO 8601 timestamp."""
    if '.' in stamp:
        return datetime.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S.%f%z')
    if 'Z' in stamp:
        return datetime.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S%z')
    if '+' in stamp:
        return datetime.datetime.fromisoformat(stamp)
    return datetime.datetime.strptime(stamp + 'Z', '%Y-%m-%dT%H:%M:%S%z')


def unsafe_path(path: str) -> bool:
    """Returns True if the path contains some chars that are problematic in URLs."""
    return not SAFE_CHARS_RE.search(path)


def strip_xmlns(tag: str) -> str:
    """Strip the XML namespace portion of a tag."""
    if not tag.startswith('{'):
        return tag  # No XMLNS
    if (i := tag.find('}')) < 0:
        return tag  # Invalid XMLNS
    return tag[i + 1:]


def substitute_el_expression(text: str, props: dict[str, str]) -> str:
    """Perform simple Java EL-expression substitution on a text.

    This performs only simple variable replacements.

    Args:
        text: templated text string
        props: property strings to replace
    """
    # TODO: It's not clear if this needs to be performed recursively on each string to handle
    # templates within templates.
    def replace_property(regex) -> str:
        if regex.group(1) in props:
            return props[regex.group(1)]
        logging.info('Parse error: cannot find property %s', regex.group(1))
        return ''

    return EL_EXPRESSION_RE.sub(replace_property, text)


def parse_pom(xml: str) -> list[str]:
    """Parse a Maven POM file to extract useful info.

    Only basic EL template replacement is performed, on the given properties and only the elements
    found to be typically used in POM file.
    """
    ns = {'x': 'http://maven.apache.org/POM/4.0.0'}
    root = ET.fromstring(xml)

    # Load the properties needed for ${...} template substitution
    # Some additional properties are added below from common tags
    properties = {}  # type: dict[str, str]
    if (props := root.find('x:properties', ns)) is not None:
        for prop in props:
            key = strip_xmlns(prop.tag)
            if key:
                properties[key] = prop.text

    # Get the URLs we are here for
    rawurls = []  # type: list[str]
    if (tag := root.find('x:url', ns)) is not None:
        rawurls.append(tag.text)
        properties['project.url'] = tag.text

    if (el_scm := root.find('x:scm', ns)) is not None:
        if (tag := el_scm.find('x:url', ns)) is not None:
            rawurls.append(tag.text)
        if (tag := el_scm.find('x:tag', ns)) is not None:
            properties['project.scm.tag'] = tag.text

    if (tag := root.find('x:artifactId', ns)) is not None:
        properties['project.artifactId'] = tag.text

    if (tag := root.find('x:version', ns)) is not None:
        properties['project.version'] = tag.text

    # Template substitution on all URLs
    return [substitute_el_expression(url, properties) for url in rawurls]


def extract_link(text: str) -> str:
    """Find a URL in a snippet of plain text."""
    match = TEXT_LINK_RE.search(text)
    if match:
        return match.group(0)
    return ''


class SavannahParser(html.parser.HTMLParser):
    """Parser for GNU Savannah HTML pages.

    Date is available in this style of tree:
      <h2>Latest News</h2><span class="smaller">xxx<a>proj</a>HERE IS THE DATE</span>
    """
    def __init__(self):
        super().__init__()
        self.date = ''        # Extracted date
        self.urls = []        # List of extracted URLs
        self.current_url = ''
        self.getdate = 0      # How close we are to getting the date

    def handle_starttag(self, tag: str, attrs):
        self.current_url = ''
        if tag == 'a':
            attr_dict = dict(attrs)
            if 'tabs' in set(attr_dict.get('class', '').split()):
                self.current_url = attr_dict.get('href', '')

        elif self.getdate == 1 and tag == 'span':
            attr_dict = dict(attrs)
            if 'smaller' in set(attr_dict.get('class', '').split()):
                self.getdate = 2

    def handle_startendtag(self, tag: str, attrs):
        self.current_url = ''
        if tag == 'span':
            self.getdate = 0

    def handle_endtag(self, tag: str):
        self.current_url = ''
        if tag == 'span':
            self.getdate = 0

        elif self.getdate == 2 and tag == 'a':
            self.getdate = 3

    def handle_data(self, data: str):
        if self.current_url and data.strip() == 'Homepage':
            self.urls.append(self.current_url)

        elif data.strip().startswith('Latest News'):
            self.getdate = 1

        elif self.getdate == 3:
            self.date = data.strip().lstrip(', ')
            self.getdate = 0


@contextlib.contextmanager
def setctimelocale():
    """Context manager to use the "C" LC_TIME locale.

    This allows parsing standard time formats without locale-specifics interfering.
    The thread lock avoids the temporary locale change from affecting other threads
    AS LONG AS ALL LOCALE-DEPENDENT CALLS ARE LOCKED WITH THIS SAME MUTEX.
    This context manager can only prevent other calls to this same context manager
    from interfering with each other. This is brittle, and it's probably better that
    the program simply switch to the C locale at startup and leave it there, simply
    eschewing the use of other locales altogether.
    """
    with LOCALE_LOCK:
        saved = locale.setlocale(locale.LC_TIME)
        try:
            yield locale.setlocale(locale.LC_TIME, 'C')
        finally:
            locale.setlocale(locale.LC_TIME, saved)


def parse_savannah(html: str) -> Optional[ProjInfo]:
    """Parse a Savannah page to extract useful info.

    Savannah doesn't appear to offer an API for extracting this info, so screen-scrape it.
    """
    parser = SavannahParser()
    parser.feed(html)

    # TODO: find a better status
    status = ProjInfo.ProjStatus.UNKNOWN
    # Date looks like: Thu 11 Feb 2010 10:29:00 PM UTC
    try:
        with setctimelocale():
            last_modified = datetime.datetime.strptime(parser.date + '+0000',
                                                       '%a %d %b %Y %I:%M:%S %p UTC%z')
    except ValueError:
        logging.warning('Unsupported date format %s', parser.date)
        last_modified = None
    urls = [url for url in parser.urls if url]
    return ProjInfo(status=status, last_modified=last_modified, urls=urls)


class OcamlParser(html.parser.HTMLParser):
    """Parser for opam.ocaml.org HTML pages."""
    def __init__(self):
        super().__init__()
        self.urls = []        # List of extracted URLs
        self.date = ''        # Extracted date
        self.in_th = False
        self.in_interesting_url = False

    def handle_starttag(self, tag: str, attrs):
        self.in_th = tag == 'th'
        if self.in_interesting_url and tag == 'a':
            attr_dict = dict(attrs)
            self.urls.append(attr_dict.get('href', ''))

        elif tag == 'time':
            attr_dict = dict(attrs)
            self.date = attr_dict.get('datetime', '')

    def handle_data(self, data: str):
        self.in_interesting_url = (self.in_th and data.strip()
                                   in frozenset({'Homepage', 'Source  [http]', 'Source [http]'}))

    def handle_endtag(self, tag: str):
        if tag == 'tr':
            # End of entry
            self.in_th = False
            self.in_interesting_url = False


def parse_ocaml(html: str) -> Optional[ProjInfo]:
    """Parse a opam.ocaml.org page to extract useful info.

    opam2web doesn't appear to offer an API for extracting this info, so screen-scrape it.
    An alternative would be to download .opam files directly from
    https://github.com/ocaml/opam-repository/ but we'd need to figure out which is the
    latest version ourselves somehow.
    """
    parser = OcamlParser()
    parser.feed(html)

    # TODO: find a better status
    status = ProjInfo.ProjStatus.UNKNOWN
    try:
        last_modified = datetime.datetime.strptime(parser.date + '+0000', '%Y-%m-%d%z')
    except ValueError:
        logging.warning('Unsupported date format %s', parser.date)
        last_modified = None
    urls = [url for url in parser.urls if url]
    return ProjInfo(status=status, last_modified=last_modified, urls=urls)


def get_pagure_repo(url: str) -> str:
    """Return the repo or namespace/repo to use from a Pagure URL.

    Since it can be a two level name, use heuristics to try to figure out which one it is.
    Unfortunately, it may not be perfect.
    """
    scheme, netloc, path, query, fragment = parse.urlsplit(url)
    parts = path.split('/')

    # Empty
    if len(parts) < 2:
        return ''

    # One level
    # Make sure it's not a special top-level name
    # We might be able to derive the repo from the rest of the URL, but it's not currently
    # worth the bother.
    if parts[1] in frozenset({'api', 'docs', 'fork', 'user'}):
        return ''

    if len(parts) == 2 or len(parts) == 3 and not parts[2]:
        return parts[1]

    # Possibly Two levels
    # If the second level is a magic name, it's actually just one level
    if parts[2] in frozenset({'archive', 'blame', 'blob', 'boards', 'branches', 'c' 'commits',
                              'forks', 'history', 'issue', 'issues', 'pull-request',
                              'pull-requests', 'raw', 'releases', 'roadmap', 'stats', 'tree'}):
        return parts[1]

    # We assume that a URL on the releases host points to a file, so it needs one more
    # URL part (the file name) than the other hosts. This isn't a perfect heuristic but
    # it should be generally more accurate.
    if (netloc.lower() == 'releases.pagure.org'
       and (len(parts) == 3 or len(parts) == 4 and not parts[3])):
        return parts[1]

    # Two levels
    return f'{parts[1]}/{parts[2]}'


class HostingAPI:
    """API to obtain project information from various project hosting sites."""

    def __init__(self, gh_token: Optional[str]):
        self.req = netreq.Session()
        self.gh_token = gh_token
        # Initialize the cache here to avoid memory leaks (see flake8 issue B019)
        self.get_project_info = functools.lru_cache(maxsize=100)(self._get_project_info)

    def _get_generic_project_name(self, url: str) -> tuple[str, str]:
        """Return the source code owner and project to use from a source hosting system URL.

        This extracts them only from the source repository URL.  This currently supports GitHub
        URLs and others with a similar format (like GitLab).
        """
        scheme, netloc, path, query, fragment = parse.urlsplit(url)
        parts = path.split('/')
        # Sanity check URL
        if len(parts) < 3:
            logging.warning('Unsupported repository URL %s', url)
            return ('', '')
        return tuple(path.split('/')[1:3])

    def get_gh_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves interesting metadata about a Github project.

        See https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#get-a-repository
        Args:
            url: the canonical URL for the GitHub project
        """
        owner, repo = self._get_generic_project_name(url)
        if not owner or not repo or unsafe_path(owner) or unsafe_path(repo):
            return None

        headers = {'Accept': GH_DATA_TYPE,
                   'X-GitHub-Api-Version': GH_API_VERSION,
                   'User-Agent': netreq.USER_AGENT
                   }
        if self.gh_token:
            headers['Authorization'] = 'Bearer ' + self.gh_token
        resp = self.req.get(GH_BASE_URL.format(owner=owner, repo=repo), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None

        meta = json.loads(resp.text)
        status = ProjInfo.ProjStatus.INVALID if meta['archived'] else ProjInfo.ProjStatus.VALID
        last_modified = parse_iso8601(meta['pushed_at'])
        urls = [meta['homepage']] if meta['homepage'] else []
        # html_url could be different from that requested if the repository was redirected
        if meta['html_url'] and (owner, repo) != self._get_generic_project_name(meta['html_url']):
            urls.append(meta['html_url'])
        if meta['fork']:
            # TODO: maybe this information should be put into ProjInfo instead
            logging.info('Note: project is not original but a fork (%s)', url)
        return ProjInfo(
            status=status,
            last_modified=last_modified,
            urls=urls)

    def get_gh_releases(self, url: str) -> list[str]:
        """Retrieves a list of release tags for a Github project.

        See https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#list-releases

        Args:
            url: the canonical URL for the GitHub project
        """
        owner, repo = self._get_generic_project_name(url)
        if not owner or not repo or unsafe_path(owner) or unsafe_path(repo):
            return []

        headers = {'Accept': GH_DATA_TYPE,
                   'X-GitHub-Api-Version': GH_API_VERSION,
                   'User-Agent': netreq.USER_AGENT
                   }
        if self.gh_token:
            headers['Authorization'] = 'Bearer ' + self.gh_token
        resp = self.req.get(GH_RELEASES_URL.format(owner=owner, repo=repo), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return []
        return [r['tag_name'] for r in json.loads(resp.text)]

    def get_gh_tags(self, url: str) -> list[str]:
        """Retrieves a list of tags for a Github project.

        See https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#list-repository-tags

        Args:
            url: the canonical URL for the GitHub project
        """
        owner, repo = self._get_generic_project_name(url)
        if not owner or not repo or unsafe_path(owner) or unsafe_path(repo):
            return []

        headers = {'Accept': GH_DATA_TYPE,
                   'X-GitHub-Api-Version': GH_API_VERSION,
                   'User-Agent': netreq.USER_AGENT
                   }
        if self.gh_token:
            headers['Authorization'] = 'Bearer ' + self.gh_token
        resp = self.req.get(GH_TAGS_URL.format(owner=owner, repo=repo), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return []
        return [r['name'] for r in json.loads(resp.text)]

    def _get_gitlab_info(self, base_url_tmpl: str, pages_url_tmpl: str, inactive_url_tmpl: str,
                         url: str) -> Optional[ProjInfo]:
        """Retrieves the home page URL set for a Gitlab project.

        See https://docs.gitlab.com/api/rest/

        Args:
            base_url_tmpl: base API URL template
            pages_url_tmpl: project web pages URL template
            inactive_url_tmpl: inactive page search template
            url: the canonical URL for the Gitlab project
        """
        namespace, project = self._get_generic_project_name(url)
        if not namespace or not project or unsafe_path(namespace) or unsafe_path(project):
            return None

        urls = []
        last_modified = None
        status = ProjInfo.ProjStatus.UNKNOWN
        # Some Gitlab instances don't allow access to the API, so just provide the Pages links
        if base_url_tmpl:
            headers = {'Accept': JSON_DATA_TYPE,
                       'User-Agent': netreq.USER_AGENT
                       }
            resp = self.req.get(base_url_tmpl.format(namespace=namespace, project=project),
                                headers=headers, timeout=netreq.TIMEOUT)
            try:
                resp.raise_for_status()
            except netreq.HTTPError as e:
                logging.info('Error retrieving data for %s (%s: %s)',
                             url, e.response.status_code, e.response.reason)
            else:
                meta = json.loads(resp.text)
                if desc := meta['description']:
                    # Look for a link in the project description. This might
                    # not actually be a link to a home page (it might be to a
                    # related project or a specification or something) but some
                    # use it for this purpose and it's probably more likely to
                    # be right than wrong.
                    urls.append(extract_link(desc))
                last_modified = parse_iso8601(meta['last_activity_at'])

                # This field is documented to be there but in practise doesn't seem to be. Maybe
                # it's only available when authenticated?
                if 'archived' in meta:
                    status = (ProjInfo.ProjStatus.INVALID if meta['archived']
                              else ProjInfo.ProjStatus.VALID)
                elif inactive_url_tmpl:
                    # Make a separate call to see if it's inactive
                    resp = self.req.get(inactive_url_tmpl.format(
                                        namespace=namespace, project=project),
                                        headers=headers, timeout=netreq.TIMEOUT)
                    try:
                        resp.raise_for_status()
                    except netreq.HTTPError as e:
                        logging.info('Error retrieving data for %s (%s: %s)',
                                     url, e.response.status_code, e.response.reason)
                    else:
                        inactive = json.loads(resp.text)
                        for found in inactive:
                            if found['path_with_namespace'] == f'{namespace}/{project}':
                                status = ProjInfo.ProjStatus.INVALID
                                break
                        else:
                            # If site does not appear in the search, it must be active
                            status = ProjInfo.ProjStatus.VALID

        # Some projects have a "GitLab Pages" link in their project overview page but it isn't
        # included in the project's JSON dump. Until we can figure out how to tell when it's
        # active, just add it unconditionally.
        urls.append(pages_url_tmpl.format(namespace=namespace, project=project))
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def get_gitlab_com_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a Gitlab.com project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_gitlab_info(GITLAB_BASE_URL, GITLAB_COM_PAGES_URL, GITLAB_INACTIVE_URL, url)

    def get_private_gitlab_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a standardized private Gitlab project.

        Args:
            domain: the private Gitlab instance domain
            url: the canonical URL for the project
        """
        _, domain, _, _, _ = parse.urlsplit(url)
        base_api_tmpl = PRIVATE_GITLAB_BASE_URL.format(domain=domain)
        base_pages_tmpl = PRIVATE_GITLAB_PAGES_URL.format(domain=domain)
        # This is unreliable, so don't use it
        # inactive_api_tmpl = PRIVATE_GITLAB_INACTIVE_URL.format(domain=domain)
        return self._get_gitlab_info(base_api_tmpl, base_pages_tmpl, '', url)

    def _get_gitlab_tags(self, tags_url: str, url: str) -> list[str]:
        """Retrieves a list of tags for a Gitlab project.

        See https://docs.gitlab.com/api/rest/

        Args:
            tags_url: tags API URL
            url: the canonical URL for the Gitlab project
        """
        namespace, project = self._get_generic_project_name(url)
        if not namespace or not project or unsafe_path(namespace) or unsafe_path(project):
            return []

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(tags_url.format(namespace=namespace, project=project),
                            headers=headers, timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return []

        return [entry['name'] for entry in json.loads(resp.text)]

    def get_gitlab_com_tags(self, url: str) -> list[str]:
        """Retrieves a list of tags for a Gitlab.com project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_gitlab_tags(GITLAB_TAGS_URL, url)

    def get_shortpages_gitlab_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a standardized private Gitlab project.

        The pages URL doesn't have "gitlab." in the domain.

        Args:
            domain: the private Gitlab instance domain
            url: the canonical URL for the project
        """
        _, domain, _, _, _ = parse.urlsplit(url)
        bare_domain = domain.replace('gitlab.', '')
        base_api_tmpl = PRIVATE_GITLAB_BASE_URL.format(domain=domain)
        base_pages_tmpl = PRIVATE_GITLAB_PAGES_URL.format(domain=bare_domain)
        return self._get_gitlab_info(base_api_tmpl, base_pages_tmpl, '', url)

    def _get_forgejo_info(self, base_url_tmpl: str, pages_url_tmpl: str,
                          url: str) -> Optional[ProjInfo]:
        """Retrieves the home page URL set for a Forgejo project.

        See https://codeberg.org/api/swagger

        Args:
            base_url_tmpl: base API URL template
            pages_url_tmpl: project web pages URL template
            url: the canonical URL for the project
        """
        owner, repo = self._get_generic_project_name(url)
        if not owner or not repo or unsafe_path(owner) or unsafe_path(repo):
            return None

        urls = []
        last_modified = None
        status = ProjInfo.ProjStatus.UNKNOWN
        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(base_url_tmpl.format(owner=owner, repo=repo),
                            headers=headers, timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None

        meta = json.loads(resp.text)
        status = ProjInfo.ProjStatus.INVALID if meta['archived'] else ProjInfo.ProjStatus.VALID
        last_modified = parse_iso8601(meta['updated_at'])

        urls = [meta['website']] if meta['website'] else []
        # Whether a Codeberg pages site is available isn't available in the repo JSON dump,
        # so add it unconditionally.
        urls.append(pages_url_tmpl.format(owner=owner, repo=repo))

        # html_url could be different from that requested if the repository was redirected
        # (not sure if Forgejo actually does this kind of redirect)
        if meta['html_url'] and (owner, repo) != self._get_generic_project_name(meta['html_url']):
            urls.append(meta['html_url'])
        if meta['fork']:
            # TODO: maybe this information should be put into ProjInfo instead
            logging.info('Note: project is not original but a fork (%s)', url)
        return ProjInfo(
            status=status,
            last_modified=last_modified,
            urls=urls)

    def get_codeberg_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a codeberg.org project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_forgejo_info(CODEBERG_BASE_URL, CODEBERG_PAGES_URL, url)

    def get_fedoraforge_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a forge.fedoraproject.org project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_forgejo_info(FEDORAFORGE_BASE_URL, '', url)

    def _get_forgejo_tags(self, base_url_tmpl: str, url: str) -> list[str]:
        """Retrieves a list of tags for a Forgejo project.

        Args:
            base_url_tmpl: base API URL template
            url: the canonical URL for the Forgejo project
        """
        owner, repo = self._get_generic_project_name(url)
        if not owner or not repo or unsafe_path(owner) or unsafe_path(repo):
            return []

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(base_url_tmpl.format(owner=owner, repo=repo),
                            headers=headers, timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return []

        # Use tag_name if found (in releases only) otherwise name (in tags and releases)
        return [tag.get('tag_name', tag['name']) for tag in json.loads(resp.text)]

    def get_codeberg_releases(self, url: str) -> list[str]:
        """Retrieves a list of releases for a Codeberg project.

        Args:
            url: the canonical URL for the Codeberg project
        """
        return self._get_forgejo_tags(CODEBERG_RELEASES_URL, url)

    def get_fedoraforge_releases(self, url: str) -> list[str]:
        """Retrieves a list of releases for the forge.fedoraproject.org project.

        Args:
            url: the canonical URL for the the forge.fedoraproject.org project
        """
        return self._get_forgejo_tags(FEDORAFORGE_RELEASES_URL, url)

    def get_codeberg_tags(self, url: str) -> list[str]:
        """Retrieves a list of tags for a Codeberg project.

        Args:
            url: the canonical URL for the Codeberg project
        """
        return self._get_forgejo_tags(CODEBERG_TAGS_URL, url)

    def get_fedoraforge_tags(self, url: str) -> list[str]:
        """Retrieves a list of tags for the forge.fedoraproject.org project.

        Args:
            url: the canonical URL for the the forge.fedoraproject.org project
        """
        return self._get_forgejo_tags(FEDORAFORGE_TAGS_URL, url)

    def _get_pagure_info(self, base_url_tmpl: str, url: str) -> Optional[ProjInfo]:
        """Retrieves interesting metadata about a Pagure project.

        See https://pagure.io/api/0/

        Args:
            base_url_tmpl: base API URL template
            url: the canonical URL for the Pagure project
        """
        repo = get_pagure_repo(url)
        if not repo or unsafe_path(repo.replace('/', '')):
            return None

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(base_url_tmpl.format(repo=repo), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None

        meta = json.loads(resp.text)
        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN
        last_modified = datetime.datetime.fromtimestamp(int(meta['date_modified']),
                                                        tz=datetime.timezone.utc)
        # TODO: A project can set a URL, but there doesn't seem to be a way to get it via the API
        urls = []  # type: list[str]
        return ProjInfo(
            status=status,
            last_modified=last_modified,
            urls=urls)

    def get_pagureio_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves interesting metadata about a Pagure project.

        See https://pagure.io/api/0/

        Args:
            url: the canonical URL for the Pagure project
        """
        return self._get_pagure_info(PAGUREIO_BASE_URL, url)

    def get_srcfedora_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves interesting metadata about a src.fedoraproject.org project.

        Args:
            url: the canonical URL for the Pagure project
        """
        return self._get_pagure_info(SRCFEDORA_BASE_URL, url)

    def _get_pagure_tags(self, base_url_tmpl: str, url: str) -> list[str]:
        """Retrieves a list of tags for a Pagure project.

        See https://pagure.io/api/0/#projects-tab

        Args:
            base_url_tmpl: base API URL template
            url: the canonical URL for the Pagure project
        """
        repo = get_pagure_repo(url)
        if not repo or unsafe_path(repo.replace('/', '')):
            return []

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(base_url_tmpl.format(repo=repo), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return []

        return list(json.loads(resp.text)['tags'])

    def get_pagureio_tags(self, url: str) -> list[str]:
        """Retrieves a list of tags for a Pagure project.

        Args:
            url: the canonical URL for the Pagure project
        """
        return self._get_pagure_tags(PAGUREIO_TAGS_URL, url)

    def get_srcfedora_tags(self, url: str) -> list[str]:
        """Retrieves a list of tags for the src.fedoraproject.org project.

        Args:
            url: the canonical URL for the the src.fedoraproject.org project
        """
        return self._get_pagure_tags(SRCFEDORA_TAGS_URL, url)

    def get_pypi_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a PyPi project.

        See https://docs.pypi.org/api/json/

        Args:
            url: the canonical URL for the project
        """
        _, project = self._get_generic_project_name(url)
        if not project or unsafe_path(project):
            return None

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(PYPI_BASE_URL.format(project=project), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        meta = json.loads(resp.text)
        info = meta['info']

        urls = [info['home_page'], info['download_url']]
        proj_urls = info['project_urls']
        if proj_urls:
            # The project URLs seems to be somewhat free-form, so try a bunch that are known to
            # have been used in the wild
            keys = ['home_page', 'homepage', 'Home-page', 'Home', 'download_url', 'documentation',
                    'download', 'Homepage', 'Download', 'Docs', 'Documentation', 'Source Code',
                    'Source', 'Sources', 'source', 'GitHub: repo', 'repository', 'Repository',
                    'Code']
            urls.extend(proj_urls.get(key, '') for key in keys)

        last_modified = None
        for relinfos in meta['releases'].values():
            for relinfo in relinfos:
                stamp = parse_iso8601(relinfo['upload_time_iso_8601'])
                last_modified = max(stamp, last_modified) if last_modified else stamp

        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN
        urls = [url for url in urls if url and url != 'UKNOWN']
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def get_crates_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a crates.io project.

        See https://doc.rust-lang.org/cargo/reference/registry-index.html#index-format

        Args:
            url: the canonical URL for the project
        """
        _, crate = self._get_generic_project_name(url)
        if not crate or unsafe_path(crate):
            return None

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(CRATES_BASE_URL.format(crate=crate), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        info = json.loads(resp.text)['crate']

        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN
        last_modified = parse_iso8601(info['updated_at'])
        urls = [info['homepage'] or '', info['repository'] or '', info['documentation'] or '']
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def get_cpan_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a CPAN project.

        See https://github.com/metacpan/metacpan-api/blob/master/docs/API-docs.md

        Args:
            url: the canonical URL for the project
        """
        _, module = self._get_generic_project_name(url)
        if not module or unsafe_path(module):
            return None

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(CPAN_BASE_URL.format(module=module), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        meta = json.loads(resp.text)
        info = meta['resources']
        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN
        last_modified = parse_iso8601(meta['date'])
        urls = [info.get('homepage', ''), info.get('repository', {}).get('web', '')]
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def get_sf_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a SourceForge project.

        See https://sourceforge.net/api-docs/#operation/GET_neighborhood-project

        Args:
            url: the canonical URL for the project
        """
        _, project = self._get_generic_project_name(url)
        if not project or unsafe_path(project):
            return None

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(SF_BASE_URL.format(project=project), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        info = json.loads(resp.text)

        last_modified = None
        for tool in info['tools']:
            if tool['name'] == 'activity':
                resp = self.req.get(SF_ACTIVITY_URL.format(project=project), headers=headers,
                                    timeout=netreq.TIMEOUT)
                try:
                    resp.raise_for_status()
                except netreq.HTTPError as e:
                    logging.info('Error retrieving data for %s (%s: %s)',
                                 url, e.response.status_code, e.response.reason)
                else:
                    activities = json.loads(resp.text)
                    for activity in activities['timeline']:
                        # A release or a commit counts as project activity. Most other types can be
                        # created by users trying to wake a dead project. "blog" might be another
                        # we could look at, but code is king.
                        # It seems like sf.net doesn't return very old activities (like >12 years)
                        # so such old projects won't get a date returned.
                        # TODO: Work around this by using the oldest one of the non-code activities
                        # as last_modified. It's not accurate, but it puts an upper bound on
                        # the last commit or release date that is likely to be very old already.
                        # Only do this if there aren't very many activities returned, since if there
                        # are, then it's possible recent code ones were pushed off the end by
                        # even more recent other activities (like comments).
                        if 'release' in activity['tags'] or 'commit' in activity['tags']:
                            # Use the first matching activity found
                            last_modified = datetime.datetime.fromtimestamp(
                                activity['published'] / 1000, tz=datetime.timezone.utc)
                            break
                    # It looks like activity logs only go back so far, so a lack of activity
                    # could mean no activity or very old activity. Either way, it's a bad sign
                    # and so perhaps should be surfaced.

        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN

        # Could pull out sf.net-hosted CVS, SVN or GIT links, but that probably wouldn't help much
        # and we can't tell if they're active or not.
        urls = [info['external_homepage'], info['moved_to_url']]
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def _get_npm_info(self, base_url_tmpl: str, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a npm/npmjs project.

        The proper base API template must be supplied.
        See https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md

        Args:
            base_url_tmpl: base API URL template
            url: the canonical URL for the project
        """
        _, package = self._get_generic_project_name(url)
        if not package or unsafe_path(package):
            return None

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(base_url_tmpl.format(package=package), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        info = json.loads(resp.text)

        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN
        last_modified = None
        for name, timestr in info['time'].items():
            if name == 'modified':
                # There is a 'modified' field, but that also seems to be updated if a scanner
                # detects a vulnerability in a project, even if it hasn't had a release in years,
                # so it's not really what we need.
                continue
            stamp = parse_iso8601(timestr)
            last_modified = max(stamp, last_modified) if last_modified else stamp
        urls = [info.get('homepage', ''), info.get('repository', {}).get('url', '')]
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def get_npm_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a npm project.

        See https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md

        Args:
            url: the canonical URL for the project
        """
        return self._get_npm_info(NPM_BASE_URL, url)

    def get_npmjs_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a npmjs project.

        See https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md

        Args:
            url: the canonical URL for the project
        """
        return self._get_npm_info(NPMJS_BASE_URL, url)

    def get_ruby_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a Rubygems project.

        See https://guides.rubygems.org/rubygems-org-api/#gem-methods

        Args:
            url: the canonical URL for the project
        """
        _, gem = self._get_generic_project_name(url)
        if not gem or unsafe_path(gem):
            return None

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(RUBY_BASE_URL.format(gem=gem), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        info = json.loads(resp.text)
        metadata = info['metadata']
        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN
        last_modified = parse_iso8601(info['version_created_at'])
        urls = [info['source_code_uri'], info['homepage_uri'], metadata.get('homepage_uri', ''),
                metadata.get('source_code_uri'), metadata.get('documentation_uri')]
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def get_maven_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a Maven project.

        See https://central.sonatype.com/api-doc

        Args:
            url: the canonical URL for the project
        """
        _, _, path, _, _ = parse.urlsplit(url)
        parts = path.split('/')
        if len(parts) < 4:
            return None
        group, artifact = parts[2], parts[3]
        if unsafe_path(group) or unsafe_path(artifact):
            return None
        group_path = group.replace('.', '/')

        # Step 1: get the version metadata
        if MAVEN_USE_SEARCH:
            # The search API seems to have more up-to-date data than the other API
            headers = {'Accept': JSON_DATA_TYPE,
                       'User-Agent': netreq.USER_AGENT
                       }
            resp = self.req.get(MAVEN_SEARCH_URL.format(group=group, artifact=artifact),
                                headers=headers, timeout=netreq.TIMEOUT)
            try:
                resp.raise_for_status()
            except netreq.HTTPError as e:
                logging.info('Error retrieving data for %s (%s: %s)',
                             url, e.response.status_code, e.response.reason)
                return None
            info = json.loads(resp.text)['response']
            if not info or info['numFound'] != 1:
                return None
            pinfo = info['docs'][0]
            if pinfo['g'] != group or pinfo['a'] != artifact:
                # The server has given us a result which we didn't ask for
                logging.info('Mismatch in requested Maven group+artifact %s %s',
                             pinfo['g'], pinfo['a'])
                return None
            version = pinfo['latestVersion']
            last_modified = datetime.datetime.fromtimestamp(int(pinfo['timestamp']) / 1000,
                                                            tz=datetime.timezone.utc)

        else:
            headers = {'Accept': XML_DATA_TYPE,
                       'User-Agent': netreq.USER_AGENT
                       }
            resp = self.req.get(MAVEN_BASE_URL.format(group_hier=group_path, artifact=artifact),
                                headers=headers, timeout=netreq.TIMEOUT)
            try:
                resp.raise_for_status()
            except netreq.HTTPError as e:
                logging.info('Error retrieving data for %s (%s: %s)',
                             url, e.response.status_code, e.response.reason)
                return None
            # TODO: parse XML from /metadata/versioning/latest to get version
            # But this metadata source is sometimes out of date
            # version = ???
            # TODO: get timestamp from somewhere
            # last_modified = ???

        # Step 2: get the POM metadata
        resp = self.req.get(MAVEN_POM_URL.format(group_hier=group_path, artifact=artifact,
                                                 version=version),
                            headers=headers, timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None

        # Step 3: return the metadata from POM
        try:
            urls = parse_pom(resp.text)
        except ET.ParseError:
            logging.info('Could not parse POM file for %s:%s', group, artifact)
            return None

        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def get_launchpad_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves the home page set for a Launchpad project.

        Args:
            url: the canonical URL for the project
        """
        _, _, path, _, _ = parse.urlsplit(url)
        parts = path.split('/')
        if len(parts) < 2:
            return None
        project = parts[1]
        if not project or unsafe_path(project):
            return None

        headers = {'Accept': XML_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        # Retrieve main project info
        resp = self.req.get(LAUNCHPAD_BASE_URL.format(project=project),
                            headers=headers, timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        info = json.loads(resp.text)
        urls = [info.get('homepage_url', '')]

        # Retrieve the timeline to get release dates
        resp = self.req.get(LAUNCHPAD_OP_URL.format(
            project=project, op='get_timeline', extra='&include_inactive=false'),
            headers=headers, timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None

        # Find the most recent date of all releases.
        # The API might not give us everything, but they should be in reverse order,
        # so we might be able to get away with just using the first one found.
        last_modified = None
        timeline = json.loads(resp.text)
        for entry in timeline['entries']:
            for landmark in entry['landmarks']:
                if landmark['date']:
                    lm_date = datetime.datetime.strptime(landmark['date'] + 'Z', '%Y-%m-%d%z')
                    last_modified = max(last_modified, lm_date) if last_modified else lm_date

        status = ProjInfo.ProjStatus.VALID if info['active'] else ProjInfo.ProjStatus.INVALID
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def _get_savannah_info(self, base_url_tmpl: str, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a GNU Savannah project.

        Args:
            base_url_tmpl: base API URL template
            url: the canonical URL for the project
        """
        _, project = self._get_generic_project_name(url)
        if not project or unsafe_path(project):
            return None

        headers = {'Accept': HTML_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(base_url_tmpl.format(project=project), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        return parse_savannah(resp.text)

    def get_gnusavannah_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a GNU Savannah project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_savannah_info(GNUSV_BASE_URL, url)

    def get_nongnusavannah_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a Non-GNU Savannah project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_savannah_info(NONGNUSV_BASE_URL, url)

    def get_ocaml_info(self, url: str) -> Optional[ProjInfo]:
        """Retrieves info for a opam entry.

        Args:
            url: the canonical URL for the project
        """
        _, package = self._get_generic_project_name(url)
        if not package or unsafe_path(package):
            return None

        headers = {'Accept': HTML_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(OPAM_BASE_URL.format(package=package), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        return parse_ocaml(resp.text)

    def get_readthedocs_info(self, url: str) -> Optional[ProjInfo]:
        """Parse a ReadTheDocs page to extract useful info.

        See https://docs.readthedocs.com/platform/stable/api/v3.html
        TODO: https://readthedocs.org/docs/XXX/ is another form of URL

        Args:
            url: the canonical URL for the project
        """
        _, netloc, _, _, _ = parse.urlsplit(url)
        hosts = netloc.split('.')
        if not hosts or len(hosts) != 3:
            return None
        project = hosts[0]

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(READTHEDOCS_BASE_URL.format(project=project), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        info = json.loads(resp.text)
        homepage = info['homepage']
        repo = info.get('repository', {}).get('url')
        if repo.endswith('.git'):
            repo = repo[:-4]
        urls = [homepage, repo]

        # TODO: find a better status
        status = ProjInfo.ProjStatus.UNKNOWN
        last_modified = parse_iso8601(info['modified'])
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def get_googlecode_info(self, url: str) -> Optional[ProjInfo]:
        """Parse a Google Code archive page to extract useful info.

        Args:
            url: the canonical URL for the project
        """
        _, _, path, _, _ = parse.urlsplit(url)
        parts = path.split('/')
        if len(parts) < 3:
            return None
        project = parts[2]
        if not project or unsafe_path(project):
            return None

        headers = {'Accept': JSON_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(GOOGLECODE_BASE_URL.format(project=project), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        meta = json.loads(resp.text)

        # This seems to be the time the project was archived, which isn't terribly useful but
        # technically correct. It's also long ago now (April 2016) that the project will be
        # considered stale, which is the goal of this data.
        last_modified = parse_iso8601(meta['updated'])
        # Google Code is entirely archived, but double check just in case it ever comes back from
        # the dead
        status = (ProjInfo.ProjStatus.INVALID if meta['bucket'] == 'google-code-archive'
                  else ProjInfo.ProjStatus.UNKNOWN)

        resp = self.req.get(GOOGLECODE_INFO_URL.format(project=project), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return None
        info = json.loads(resp.text)

        urls = [info['movedTo']]
        urls = [url for url in urls if url]
        return ProjInfo(status=status, last_modified=last_modified, urls=urls)

    def _get_project_info(self, url: str) -> Optional[ProjInfo]:
        """Return basic information about a hosted project."""
        if not url:
            return None

        _, netloc, _, _, _ = parse.urlsplit(url)

        if netloc == 'github.com':
            return self.get_gh_info(url)

        if netloc == 'gitlab.com':
            return self.get_gitlab_com_info(url)

        # invent.kde.org is a gitlab instance, but doesn't provide any useful metadata in the
        # Gitlab project, and doesn't seem to have consistent pages URLs.
        # salsa.debian.org doesn't seem to have any pages URLs
        # This one works for applications but not other parts of the project:
        #   https://apps.kde.org/{{project}}
        if netloc in frozenset({'gitlab.gnome.org', 'gitlab.matrix.org', 'gitlab.xiph.org',
                                'gitlab.inria.fr', 'gitlab.dkrz.de', 'gitlab.cern.ch',
                                'gitlab.haskell.org'}):
            return self.get_private_gitlab_info(url)

        if netloc in frozenset({'gitlab.freedesktop.org', 'gitlab.xfce.org'}):
            return self.get_shortpages_gitlab_info(url)

        if netloc == 'codeberg.org':
            return self.get_codeberg_info(url)

        if netloc == 'forge.fedoraproject.org':
            return self.get_fedoraforge_info(url)

        if netloc == 'pagure.io':
            return self.get_pagureio_info(url)

        if netloc == 'src.fedoraproject.org':
            return self.get_srcfedora_info(url)

        if netloc == 'pypi.org':
            return self.get_pypi_info(url)

        if netloc == 'crates.io':
            return self.get_crates_info(url)

        if netloc == 'metacpan.org':
            return self.get_cpan_info(url)

        if netloc == 'sourceforge.net':
            return self.get_sf_info(url)

        if netloc == 'npmjs.org':
            return self.get_npm_info(url)

        if netloc == 'npmjs.com':
            return self.get_npmjs_info(url)

        if netloc == 'rubygems.org':
            return self.get_ruby_info(url)

        if netloc == 'central.sonatype.com':
            return self.get_maven_info(url)

        if netloc == 'launchpad.net':
            return self.get_launchpad_info(url)

        if netloc == 'savannah.gnu.org':
            return self.get_gnusavannah_info(url)

        if netloc == 'savannah.nongnu.org':
            return self.get_nongnusavannah_info(url)

        if netloc == 'opam.ocaml.org':
            return self.get_ocaml_info(url)

        if netloc.endswith('.readthedocs.org') or netloc.endswith('.readthedocs.io'):
            return self.get_readthedocs_info(url)

        if netloc == 'code.google.com':
            return self.get_googlecode_info(url)

        # TODO: add these sources:
        # https://hackage.haskell.org/ (home page, source code)
        # https://pecl.php.net/ (home page, source code)
        #  lower-case package name in REST API
        #  see https://pear.php.net/manual/en/core.rest.php
        #  get https://pear.php.net/rest/r/mdb2/latest.txt for version
        #  then https://pear.php.net/rest/r/mdb2/2.5.0b5.xml for info
        #  or https://pear.php.net/rest/r/mdb2/v2.2.5.0b5.xml (with v2. prefix)
        #  or https://pear.php.net/rest/r/mdb2/package.2.5.0b5.xml
        #  or https://pear.php.net/rest/p/mdb2/info.xml
        #  BUT the links aren't there!
        # https://cran.r-project.org/ (uncategorized links) can't see an API
        # NOT https://www.stackage.org/ doesn't seem to have any relevant links
        # NOT https://www.gnu.org/software/coreutils/ (probably means screen scraping &
        # that link should be enough to disambiguate)

        logging.debug('External requests not supported for %s', netloc)
        return None


if __name__ == '__main__':
    # Debugging tool
    logging.basicConfig(level=logging.DEBUG)
    h = HostingAPI(None)
    for url in sys.argv[1:]:
        # TODO: this expects canonicalized URLs
        print(h.get_project_info(url), url)
