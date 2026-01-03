"""API to access external code hosting providers."""

import functools
import html.parser
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
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

# Note this is a two-stage template: first state is to replace the domain only
PRIVATE_GITLAB_API_URL = 'https://{domain}/api/v4'
PRIVATE_GITLAB_BASE_URL = PRIVATE_GITLAB_API_URL + '/projects/{{namespace}}%2F{{project}}'
# Note this is a two-stage template: first state is to replace the domain only
PRIVATE_GITLAB_PAGES_URL = 'https://{{namespace}}.pages.{domain}/{{project}}'

LAUNCHPAD_API_URL = 'https://launchpad.net'
LAUNCHPAD_BASE_URL = LAUNCHPAD_API_URL + '/{project}/+rdf'

GNUSV_API_URL = 'https://savannah.gnu.org'
GNUSV_BASE_URL = GNUSV_API_URL + '/projects/{project}'

NONGNUSV_API_URL = 'https://savannah.nongnu.org'
NONGNUSV_BASE_URL = NONGNUSV_API_URL + '/projects/{project}'

OPAM_API_URL = 'https://opam.ocaml.org/packages'
OPAM_BASE_URL = OPAM_API_URL + '/{package}/'

READTHEDOCS_API_URL = 'https://app.readthedocs.org/api/v3/'
READTHEDOCS_BASE_URL = READTHEDOCS_API_URL + '/projects/{project}/'

# Characters that are safe in URLs without special handling
SAFE_CHARS_RE = re.compile(r'^[-a-zA-Z0-9()._!^]*$')

# EL expression parser
EL_EXPRESSION_RE = re.compile(r'\${([^}]*)}')

# RE to find a link in plain text
TEXT_LINK_RE = re.compile(r'(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])')


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
    """Parse a Maven POM file to extract useful URLS.

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
    urls = []  # type: list[str]
    if (tag := root.find('x:url', ns)) is not None:
        urls.append(tag.text)
        properties['project.url'] = tag.text

    if (el_scm := root.find('x:scm', ns)) is not None:
        if (tag := el_scm.find('x:url', ns)) is not None:
            urls.append(tag.text)
        if (tag := el_scm.find('x:tag', ns)) is not None:
            properties['project.scm.tag'] = tag.text

    if (tag := root.find('x:artifactId', ns)) is not None:
        properties['project.artifactId'] = tag.text

    if (tag := root.find('x:version', ns)) is not None:
        properties['project.version'] = tag.text

    # Template substitution on all URLs
    return [substitute_el_expression(url, properties) for url in urls]


def parse_lp_rdf(xml: str) -> list[str]:
    """Parse a Launchpad.net RDF file to extract useful URLS."""
    ns = {'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
          'lp': 'https://launchpad.net/rdf/launchpad#'}
    resource_tag = f'{{{ns["rdf"]}}}resource'
    root = ET.fromstring(xml)
    urls = []
    if ((el_product := root.find('lp:Product', ns)) is not None
        and (el_homepage := el_product.find('lp:homepage', ns)) is not None
            and (homepage := el_homepage.attrib.get(resource_tag, ''))):
        urls.append(homepage)
    return urls


def extract_link(text: str) -> str:
    """Find a URL in a snippet of plain text."""
    match = TEXT_LINK_RE.search(text)
    if match:
        return match.group(0)
    return ''


class SavannahParser(html.parser.HTMLParser):
    """Parser for GNU Savannah HTML pages."""
    def __init__(self):
        super().__init__()
        self.urls = []
        self.current_url = ''

    def handle_starttag(self, tag: str, attrs):
        self.current_url = ''
        if tag == 'a':
            attr_dict = dict(attrs)
            if 'tabs' in set(attr_dict.get('class', '').split()):
                self.current_url = attr_dict.get('href', '')

    def handle_startendtag(self, tag: str, attrs):
        self.current_url = ''

    def handle_endtag(self, tag: str):
        self.current_url = ''

    def handle_data(self, data: str):
        if self.current_url and data.strip() == 'Homepage':
            self.urls.append(self.current_url)


def parse_savannah(html: str) -> list[str]:
    """Parse a Savannah page to extract useful URLS.

    Savannah doesn't appear to offer an API for extracting this info, so screen-scrape it.
    """
    parser = SavannahParser()
    parser.feed(html)
    return parser.urls


class OcamlParser(html.parser.HTMLParser):
    """Parser for opam.ocaml.org HTML pages."""
    def __init__(self):
        super().__init__()
        self.urls = []
        self.in_th = False
        self.in_interesting_url = False

    def handle_starttag(self, tag: str, attrs):
        self.in_th = tag == 'th'
        if self.in_interesting_url and tag == 'a':
            attr_dict = dict(attrs)
            self.urls.append(attr_dict.get('href', ''))

    def handle_data(self, data: str):
        self.in_interesting_url = (self.in_th and data.strip()
                                   in frozenset({'Homepage', 'Source  [http]', 'Source [http]'}))

    def handle_endtag(self, tag: str):
        if tag == 'tr':
            # End of entry
            self.in_th = False
            self.in_interesting_url = False


def parse_ocaml(html: str) -> list[str]:
    """Parse a opam.ocaml.org page to extract useful URLS.

    opam2web doesn't appear to offer an API for extracting this info, so screen-scrape it.
    An alternative would be to download .opam files directly from
    https://github.com/ocaml/opam-repository/ but we'd need to figure out which is the
    latest version ourselves somehow.
    """
    parser = OcamlParser()
    parser.feed(html)
    return parser.urls


class HostingAPI:
    """API to obtain project information from various project hosting sites."""

    def __init__(self, gh_token: Optional[str]):
        self.req = netreq.Session()
        self.gh_token = gh_token
        # Initialize the cache here to avoid memory leaks (see flake8 issue B019)
        self.get_project_links = functools.lru_cache(maxsize=100)(self._get_project_links)

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

    def get_gh_url(self, url: str) -> str:
        """Retrieves the home page URL set for a Github project.

        See https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#get-a-repository
        Args:
            url: the canonical URL for the GitHub project
        """
        owner, repo = self._get_generic_project_name(url)
        if not owner or not repo or unsafe_path(owner) or unsafe_path(repo):
            return ''

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
            return ''
        return json.loads(resp.text)['homepage']

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

    def _get_gitlab_url(self, base_url_tmpl: str, pages_url_tmpl: str, url: str) -> list[str]:
        """Retrieves the home page URL set for a Gitlab project.

        See https://docs.gitlab.com/api/rest/

        Args:
            base_url_tmpl: base API URL template
            pages_url_tmpl: project web pages URL template
            url: the canonical URL for the Gitlab project
        """
        namespace, project = self._get_generic_project_name(url)
        if not namespace or not project or unsafe_path(namespace) or unsafe_path(project):
            return []

        urls = []
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
                if desc := json.loads(resp.text)['description']:
                    urls.append(extract_link(desc))

        # Look for a link in the project description. This might not actually be a link to a
        # home page (it might be to a related project or a specification or something) but
        # some use it for this purpose and it's probably more likely to be right than wrong.
        #
        # Some projects have a "GitLab Pages" link in their project overview page but it isn't
        # included in the project's JSON dump. Until we can figure out how to tell when it's
        # active, just add it unconditionally.
        return urls + [pages_url_tmpl.format(namespace=namespace, project=project)]

    def get_gitlab_com_url(self, url: str) -> list[str]:
        """Retrieves the home page URL set for a Gitlab.com project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_gitlab_url(GITLAB_BASE_URL, GITLAB_COM_PAGES_URL, url)

    def get_private_gitlab_url(self, url: str) -> list[str]:
        """Retrieves the home page URL set for a standardized private Gitlab project.

        Args:
            domain: the private Gitlab instance domain
            url: the canonical URL for the project
        """
        _, domain, _, _, _ = parse.urlsplit(url)
        base_api_tmpl = PRIVATE_GITLAB_BASE_URL.format(domain=domain)
        base_pages_tmpl = PRIVATE_GITLAB_PAGES_URL.format(domain=domain)
        return self._get_gitlab_url(base_api_tmpl, base_pages_tmpl, url)

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

    def get_shortpages_gitlab_url(self, url: str) -> list[str]:
        """Retrieves the home page URL set for a standardized private Gitlab project.

        The pages URL doesn't have "gitlab." in the domain.

        Args:
            domain: the private Gitlab instance domain
            url: the canonical URL for the project
        """
        _, domain, _, _, _ = parse.urlsplit(url)
        bare_domain = domain.replace('gitlab.', '')
        base_api_tmpl = PRIVATE_GITLAB_BASE_URL.format(domain=domain)
        base_pages_tmpl = PRIVATE_GITLAB_PAGES_URL.format(domain=bare_domain)
        return self._get_gitlab_url(base_api_tmpl, base_pages_tmpl, url)

    def get_pypi_url(self, url: str) -> list[str]:
        """Retrieves the home page and download URLs set for a PyPi project.

        See https://docs.pypi.org/api/json/

        Args:
            url: the canonical URL for the project
        """
        _, project = self._get_generic_project_name(url)
        if not project or unsafe_path(project):
            return []

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
            return []
        info = json.loads(resp.text)['info']

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

        return [url for url in urls if url and url != 'UKNOWN']

    def get_crates_url(self, url: str) -> list[str]:
        """Retrieves the home page, repository and download URLs set for a crates.io project.

        See https://doc.rust-lang.org/cargo/reference/registry-index.html#index-format

        Args:
            url: the canonical URL for the project
        """
        _, crate = self._get_generic_project_name(url)
        if not crate or unsafe_path(crate):
            return []

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
            return []
        info = json.loads(resp.text)['crate']
        return [info['homepage'] or '', info['repository'] or '', info['documentation'] or '']

    def get_cpan_url(self, url: str) -> list[str]:
        """Retrieves the home page and download URLs set for a CPAN project.

        See https://github.com/metacpan/metacpan-api/blob/master/docs/API-docs.md

        Args:
            url: the canonical URL for the project
        """
        _, module = self._get_generic_project_name(url)
        if not module or unsafe_path(module):
            return []

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
            return []
        info = json.loads(resp.text)['resources']
        return [info.get('homepage', ''), info.get('repository', {}).get('web', '')]

    def get_sf_url(self, url: str) -> list[str]:
        """Retrieves the home page and download URLs set for a SourceForge project.

        See https://sourceforge.net/api-docs/#operation/GET_neighborhood-project

        Args:
            url: the canonical URL for the project
        """
        _, project = self._get_generic_project_name(url)
        if not project or unsafe_path(project):
            return []

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
            return []
        info = json.loads(resp.text)
        # Could pull out sf.net-hosted CVS, SVN or GIT links, but that probably wouldn't help much
        # and we can't tell if they're active or not.
        return [info['external_homepage'], info['moved_to_url']]

    def _get_npm_url(self, base_url_tmpl: str, url: str) -> list[str]:
        """Retrieves the home page and download URLs set for a npm/npmjs project.

        The proper base API template must be supplied.
        See https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md

        Args:
            base_url_tmpl: base API URL template
            url: the canonical URL for the project
        """
        _, package = self._get_generic_project_name(url)
        if not package or unsafe_path(package):
            return []

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
            return []
        info = json.loads(resp.text)
        return [info.get('homepage', ''), info.get('repository', {}).get('url', '')]

    def get_npm_url(self, url: str) -> list[str]:
        """Retrieves the home page and download URLs set for a npm project.

        See https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md

        Args:
            url: the canonical URL for the project
        """
        return self._get_npm_url(NPM_BASE_URL, url)

    def get_npmjs_url(self, url: str) -> list[str]:
        """Retrieves the home page and download URLs set for a npmjs project.

        See https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md

        Args:
            url: the canonical URL for the project
        """
        return self._get_npm_url(NPMJS_BASE_URL, url)

    def get_ruby_url(self, url: str) -> list[str]:
        """Retrieves the home page and download URLs set for a Rubygems project.

        See https://guides.rubygems.org/rubygems-org-api/#gem-methods

        Args:
            url: the canonical URL for the project
        """
        _, gem = self._get_generic_project_name(url)
        if not gem or unsafe_path(gem):
            return []

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
            return []
        info = json.loads(resp.text)
        metadata = info['metadata']
        return [info['source_code_uri'], info['homepage_uri'], metadata.get('homepage_uri', ''),
                metadata.get('source_code_uri'), metadata.get('documentation_uri')]

    def get_maven_url(self, url: str) -> list[str]:
        """Retrieves the home page and download URLs set for a Maven project.

        See https://central.sonatype.com/api-doc

        Args:
            url: the canonical URL for the project
        """
        _, _, path, _, _ = parse.urlsplit(url)
        parts = path.split('/')
        if len(parts) < 4:
            return []
        group, artifact = parts[2], parts[3]
        if unsafe_path(group) or unsafe_path(artifact):
            return []
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
                return []
            info = json.loads(resp.text)['response']
            if not info or info['numFound'] != 1:
                return []
            pinfo = info['docs'][0]
            if pinfo['g'] != group or pinfo['a'] != artifact:
                # The server has given us a result which we didn't ask for
                logging.info('Mismatch in requested Maven group+artifact %s %s',
                             pinfo['g'], pinfo['a'])
                return []
            version = pinfo['latestVersion']

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
                return []
            # TODO: parse XML from /metadata/versioning/latest to get version
            # But this metadata source is sometimes out of date

        # Step 2: get the POM metadata
        resp = self.req.get(MAVEN_POM_URL.format(group_hier=group_path, artifact=artifact,
                                                 version=version),
                            headers=headers, timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return []

        # Step 3: return the metadata from POM
        try:
            return parse_pom(resp.text)
        except ET.ParseError:
            logging.info('Could not parse POM file for %s:%s', group, artifact)
        return []

    def get_launchpad_url(self, url: str) -> list[str]:
        """Retrieves the home page set for a Launchpad project.

        Args:
            url: the canonical URL for the project
        """
        _, _, path, _, _ = parse.urlsplit(url)
        parts = path.split('/')
        if len(parts) < 2:
            return []
        project = parts[1]
        if not project or unsafe_path(project):
            return []

        headers = {'Accept': XML_DATA_TYPE,
                   'User-Agent': netreq.USER_AGENT
                   }
        resp = self.req.get(LAUNCHPAD_BASE_URL.format(project=project), headers=headers,
                            timeout=netreq.TIMEOUT)
        try:
            resp.raise_for_status()
        except netreq.HTTPError as e:
            logging.info('Error retrieving data for %s (%s: %s)',
                         url, e.response.status_code, e.response.reason)
            return []

        # Return the metadata from the RDF file
        try:
            return parse_lp_rdf(resp.text)
        except ET.ParseError:
            logging.info('Could not parse Launchpad RDF file for %s', project)
        return []

    def _get_savannah_url(self, base_url_tmpl: str, url: str) -> list[str]:
        """Retrieves the home page and download links for a GNU Savannah project.

        Args:
            base_url_tmpl: base API URL template
            url: the canonical URL for the project
        """
        _, project = self._get_generic_project_name(url)
        if not project or unsafe_path(project):
            return []

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
            return []
        return parse_savannah(resp.text)

    def get_gnusavannah_url(self, url: str) -> list[str]:
        """Retrieves the home page and download links for a GNU Savannah project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_savannah_url(GNUSV_BASE_URL, url)

    def get_nongnusavannah_url(self, url: str) -> list[str]:
        """Retrieves the home page and download links for a Non-GNU Savannah project.

        Args:
            url: the canonical URL for the project
        """
        return self._get_savannah_url(NONGNUSV_BASE_URL, url)

    def get_ocaml_url(self, url: str) -> list[str]:
        """Retrieves the home page and download links for a opam entry.

        Args:
            url: the canonical URL for the project
        """
        _, package = self._get_generic_project_name(url)
        if not package or unsafe_path(package):
            return []

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
            return []
        return parse_ocaml(resp.text)

    def get_readthedocs_url(self, url: str) -> list[str]:
        """Parse a ReadTheDocs page to extract useful URLS.

        See https://docs.readthedocs.com/platform/stable/api/v3.html
        TODO: https://readthedocs.org/docs/XXX/ is another form of URL

        Args:
            url: the canonical URL for the project
        """
        _, netloc, _, _, _ = parse.urlsplit(url)
        hosts = netloc.split('.')
        if not hosts or len(hosts) != 3:
            return []
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
            return []
        info = json.loads(resp.text)
        homepage = info['homepage']
        repo = info.get('repository', {}).get('url')
        if repo.endswith('.git'):
            repo = repo[:-4]
        return [homepage, repo]

    def _get_project_links(self, url: str) -> frozenset[str]:
        """Retrieves the home page and download URLs set at a supported code hosting project.

        This is intended to handle site that host multiple projects and not just single private
        repositories. Keeping track of individual sites it not worth the pain of keeping it
        up-to-date.

        They are returned as a frozenset so it can be cached. However, to avoid memory leaks,
        the cached function is initialized in __init__().

        Args:
            url: the canonical URL for the project
        """
        if not url:
            return frozenset()

        _, netloc, _, _, _ = parse.urlsplit(url)
        if netloc == 'github.com':
            return frozenset(filter(None, {self.get_gh_url(url)}))

        if netloc == 'gitlab.com':
            return frozenset(filter(None, self.get_gitlab_com_url(url)))

        # invent.kde.org is a gitlab instance, but doesn't provide any useful metadata in the
        # Gitlab project, and doesn't seem to have consistent pages URLs.
        # salsa.debian.org doesn't seem to have any pages URLs
        # This one works for applications but not other parts of the project:
        #   https://apps.kde.org/{{project}}
        if netloc in frozenset({'gitlab.gnome.org', 'gitlab.matrix.org', 'gitlab.xiph.org',
                                'gitlab.inria.fr', 'gitlab.dkrz.de', 'gitlab.cern.ch',
                                'gitlab.haskell.org'}):
            return frozenset(filter(None, self.get_private_gitlab_url(url)))

        if netloc in frozenset({'gitlab.freedesktop.org', 'gitlab.xfce.org'}):
            return frozenset(filter(None, self.get_shortpages_gitlab_url(url)))

        if netloc == 'pypi.org':
            return frozenset(filter(None, self.get_pypi_url(url)))

        if netloc == 'crates.io':
            return frozenset(filter(None, self.get_crates_url(url)))

        if netloc == 'metacpan.org':
            return frozenset(filter(None, self.get_cpan_url(url)))

        if netloc == 'sourceforge.net':
            return frozenset(filter(None, self.get_sf_url(url)))

        if netloc == 'npmjs.org':
            return frozenset(filter(None, self.get_npm_url(url)))

        if netloc == 'npmjs.com':
            return frozenset(filter(None, self.get_npmjs_url(url)))

        if netloc == 'rubygems.org':
            return frozenset(filter(None, self.get_ruby_url(url)))

        if netloc == 'central.sonatype.com':
            return frozenset(filter(None, self.get_maven_url(url)))

        if netloc == 'launchpad.net':
            return frozenset(filter(None, self.get_launchpad_url(url)))

        if netloc == 'savannah.gnu.org':
            return frozenset(filter(None, self.get_gnusavannah_url(url)))

        if netloc == 'savannah.nongnu.org':
            return frozenset(filter(None, self.get_nongnusavannah_url(url)))

        if netloc == 'opam.ocaml.org':
            return frozenset(filter(None, self.get_ocaml_url(url)))

        if netloc.endswith('.readthedocs.org') or netloc.endswith('.readthedocs.io'):
            return frozenset(filter(None, self.get_readthedocs_url(url)))

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
        return frozenset()


if __name__ == '__main__':
    # Debugging tool
    logging.basicConfig(level=logging.DEBUG)
    h = HostingAPI(None)
    for url in h.get_project_links(sys.argv[1]):
        print(url)
