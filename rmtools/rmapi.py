"""Python API for https://release-monitoring.org/.

See https://release-monitoring.org/static/docs/api.html
"""

import json
from typing import Any, Optional

import requests


BASE_URL = 'https://release-monitoring.org/api/v2/'


class RMApi:
    """Class for performing requests on release-monitoring.org."""

    def __init__(self, token=None):
        """Initializes the release-monitoring API object.

        token: optional API token
        """
        self.headers = {}
        if token:
            self.headers = {'Authorization': 'token ' + token}

    def get_distro_package_info(self, distro: str, package: str) -> Optional[dict[str, Any]]:
        """Returns information about a package found in a distro.

        Returns:
          a dict of info about that package, or None if package is invalid or
          has no versions
        """
        params = {'distribution': distro,
                  'name': package}
        resp = requests.get(BASE_URL + 'packages/',
                            headers=self.headers, params=params)
        resp.raise_for_status()
        r = json.loads(resp.text)
        if r['total_items'] == 0:
            return None
        assert r['total_items'] == 1
        return r['items'][0]
