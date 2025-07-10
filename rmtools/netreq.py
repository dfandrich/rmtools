"""Network request helpers."""

from typing import Optional

import requests

from . import __version__ as ver

HTTPError = requests.HTTPError

USER_AGENT = 'rmtools/' + ver

# Seconds to wait for response
TIMEOUT = 30


class Session(requests.Session):
    """Set up a requests session with a standard configuration."""

    def __init__(self, total: int = 5, backoff_factor: int = 2,
                 status_forcelist: Optional[list[int]] = None,
                 allowed_methods: Optional[list[str]] = None):
        super().__init__()
        if not status_forcelist:
            status_forcelist = [429, 500, 502, 503, 504]
        if not allowed_methods:
            allowed_methods = ['HEAD', 'GET', 'OPTIONS']

        # Experimental retry settings
        # This should delay a total of 2+4+8+16+32 seconds before aborting, by default
        retry_strategy = requests.adapters.Retry(
            total=total, backoff_factor=backoff_factor, status_forcelist=status_forcelist,
            allowed_methods=allowed_methods)
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.mount('https://', adapter)
        self.mount('http://', adapter)
