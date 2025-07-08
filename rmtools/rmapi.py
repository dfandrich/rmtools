"""Python API for https://release-monitoring.org/.

See https://release-monitoring.org/static/docs/api.html
"""

import json
import logging
from typing import Any, Optional

import requests

from . import __version__ as ver


# The base URL for API requests
BASE_URL = 'https://release-monitoring.org/api/v2/'

# Number of items to request per query; Anitya only support a maximum of 250
NUM_PER_PAGE = 250

# The absolute largest number of page requests to perform; this just avoids an infinite loop
MAX_PAGE_FAILSAFE = 1000

DATA_TYPE = 'application/json'
USER_AGENT = 'rmtools/' + ver


class Session(requests.Session):
    """Set up a requests session with a standard configuration."""

    def __init__(self, total: int = 4, backoff_factor: int = 2,
                 status_forcelist: Optional[list[int]] = None,
                 allowed_methods: Optional[list[str]] = None):
        super().__init__()
        if not status_forcelist:
            status_forcelist = [429, 500, 502, 503, 504]
        if not allowed_methods:
            allowed_methods = ['HEAD', 'GET', 'OPTIONS']

        # Experimental retry settings
        # This should delay a total of 2+4+8+16 seconds before aborting, by default
        retry_strategy = requests.adapters.Retry(
            total=total, backoff_factor=backoff_factor, status_forcelist=status_forcelist,
            allowed_methods=allowed_methods)
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.mount('https://', adapter)
        self.mount('http://', adapter)


class RMApi:
    """Class for performing requests on release-monitoring.org."""

    def __init__(self, token=None):
        """Initializes the release-monitoring API object.

        token: optional API token
        """
        self.headers = {
            'Accept': DATA_TYPE,
            'User-Agent': USER_AGENT
        }
        if token:
            self.headers.update({'Authorization': 'Token ' + token})

        self.req = Session()

    def get_paged_request_items(self, path: str, params: dict[str, str]) -> list:
        """Returns the full output of a paged request."""
        # TODO: transparently handle error retries
        items = []
        page = 1
        while page < MAX_PAGE_FAILSAFE:
            logging.debug('Requesting %s page %d', path, page)
            resp = self.req.get(BASE_URL + path + '/',
                                headers=self.headers, params=params
                                | {'items_per_page': NUM_PER_PAGE, 'page': page})
            resp.raise_for_status()
            r = json.loads(resp.text)
            items.extend(r['items'])
            if not r['items']:
                # Empty page means no more
                break
            if len(items) >= r['total_items']:
                break
            page = page + 1
        if r['total_items'] != len(items):
            logging.info('Wanted %d, got %d', r['total_items'], len(items))
        return items

    def get_distro_package_info(self, distro: str, package: str) -> Optional[dict[str, Any]]:
        """Returns information about a package found in a distro.

        Returns:
          a dict of info about that package, or None if package is invalid or
          has no versions
        """
        params = {'distribution': distro,
                  'name': package}
        resp = self.req.get(BASE_URL + 'packages/',
                            headers=self.headers, params=params)
        resp.raise_for_status()
        r = json.loads(resp.text)
        if r['total_items'] == 0:
            return None
        assert r['total_items'] == 1  # we only request a single one
        return r['items'][0]

    def find_project(self, project: str) -> list[dict]:
        """Returns information about the given project.

        If more than one project matches the name, return them all.
        """
        return self.get_paged_request_items('projects', {'name': project})

    def get_distro_packages(self, distro: str) -> set[str]:
        """Returns a list of packages for a distribution."""
        items = self.get_paged_request_items('packages', {'distribution': distro})
        return {item['name'] for item in items}

    def create_new_package(self, distro: str, project_name: str, package_name: str,
                           project_ecosystem: str):
        """Creates a new package for a given project."""
        headers = {'Content-Type': 'application/json'}
        data = {
            'distribution': distro,
            'package_name': package_name,
            'project_name': project_name,
            'project_ecosystem': project_ecosystem
        }
        resp = self.req.post(BASE_URL + 'packages/', headers=self.headers | headers,
                             data=json.dumps(data))
        resp.raise_for_status()
