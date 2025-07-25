"""API to access external sites."""

import contextlib
import functools
import html.parser
import logging
import re
import sys
from urllib import parse

from rmtools import netreq

# Regex to parse the http-equiv=refresh content
REFRESH_RE = re.compile(r'^\s*\d+\s*;\s*url\s*=\s*(.*?)\s*$')

# Largest page size to download to look for a refresh tag
REFRESH_SIZE_MAX = 2000


def parse_refresh_url(content: str) -> str:
    """Parse http-equiv=refresh text to extract the URL."""
    if r := REFRESH_RE.search(content):
        return r.group(1)
    return ''


class RefreshParser(html.parser.HTMLParser):
    """Parser for HTML pages to find refresh meta tags."""
    def __init__(self):
        super().__init__()
        self.url = ''
        self.in_head = False

    def handle_starttag(self, tag: str, attrs):
        if tag == 'head':
            self.in_head = True
            return

        if self.in_head and tag == 'meta':
            attr_dict = dict(attrs)
            if attr_dict.get('http-equiv', '').lower() == 'refresh' and 'content' in attr_dict:
                self.url = parse_refresh_url(attr_dict['content'])
                logging.debug('Redirected to %s', self.url)

    def handle_endtag(self, tag: str):
        if tag == 'head':
            self.in_head = False


def parse_refresh(text: str) -> str:
    """Parse an HTML document looking for a meta refresh tag."""
    parser = RefreshParser()
    parser.feed(text)
    return parser.url


class ExternalAPI:
    """API to obtain information from external sites."""

    def __init__(self):
        self.req = netreq.Session(total=2)
        # Initialize the cache here to avoid memory leaks (see flake8 issue B019)
        self.get_redirect = functools.lru_cache(maxsize=100)(self._get_redirect)

    def _get_redirect(self, url: str) -> str:
        """See if the URL redirects.

        If not, it returns an empty string.
        """
        scheme, _, _, _, _ = parse.urlsplit(url)
        if scheme not in frozenset({'http', 'https'}):
            # Only http and https can ever redirect
            return ''

        # Just ignore any error contacting the site; it's just best effort
        with contextlib.suppress(netreq.exceptions.RequestException):
            headers = {'User-Agent': netreq.USER_AGENT
                       }
            resp = self.req.head(url, headers=headers, allow_redirects=False, timeout=netreq.TIMEOUT)
            if resp.is_redirect:
                location = resp.headers['location']
                # Make an absolute URL from a relative one, if necessary
                return parse.urljoin(url, location)

            if resp.status_code == 200:
                # If the page looks small, it might contain a meta refresh so get it and see
                with contextlib.suppress(KeyError, ValueError):
                    if int(resp.headers['content-length']) <= REFRESH_SIZE_MAX:
                        logging.debug('Downloading page to look for a refresh tag')
                        # Retrieve the whole page and parse it
                        resp = self.req.get(url, headers=headers, allow_redirects=False,
                                            timeout=netreq.TIMEOUT)
                        if resp.status_code == 200:
                            location = parse_refresh(resp.text)
                            if not location:
                                return ''
                            # Make an absolute URL from a relative one, if necessary
                            return parse.urljoin(url, location)
                return ''

            logging.debug('Redirect check returned unexpected %d', resp.status_code)

        return ''


if __name__ == '__main__':
    # Debugging tool
    logging.basicConfig(level=logging.DEBUG)
    h = ExternalAPI()
    print(h.get_redirect(sys.argv[1]))
