"""Find projects that match a URL."""

import argparse
import logging
import re
import shlex
import sys
import time
from typing import Optional
from urllib import parse

from rmtools import add_matching
from rmtools import rmapi

# Matches a download URL
DOWNLOAD_ARCHIVE_MATCH_RE = re.compile(r'[^/]\.(tar|zip|lzh|rar|cab|tgz|tbz|txz|jar)(\.\w{1,5})?$')


def is_download_url(url: str) -> bool:
    """Looks like a download URL."""
    return not not DOWNLOAD_ARCHIVE_MATCH_RE.search(url)  # noqa: SIM208


def swap_scheme(url: str) -> str:
    """Switch the scheme from http: to https: and vice versa."""
    parsed = parse.urlparse(url)
    if parsed.scheme == 'http':
        return parse.urlunparse(parsed._replace(scheme='https'))
    if parsed.scheme == 'https':
        return parse.urlunparse(parsed._replace(scheme='http'))
    return url


def swap_www(url: str) -> str:
    """Add or remove a www from the hostname."""
    parsed = parse.urlparse(url)
    if parsed.netloc.startswith('www.'):
        return parse.urlunparse(parsed._replace(netloc=parsed.netloc[4:]))
    return parse.urlunparse(parsed._replace(netloc='www.' + parsed.netloc))


def ecosystem_name(url: str) -> Optional[tuple[str, str]]:
    """Returns the project name for a specific ecosystem from a canonical URL.

    This only works for ecosystems other than the generic, URL-specified one.
    TODO: some valid URLs that have gone through canonicalize_url() aren't in
    the expected format for this function and could return a bad result.
    """
    ecosystem = add_matching.url_ecosystem(url)
    if not ecosystem:
        return None
    u = parse.urlparse(url)
    parts = u.path.split('/')

    if ecosystem in frozenset({'pypi', 'crates.io', 'rubygems', 'npm', 'npmjs'}) and len(parts) >= 3:
        return (ecosystem, parts[2])

    return None


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
        '--delay',
        type=float,
        default=6,  # arbitrarily set to try to put a negligible load on the server
        help='Delay between successive entries (seconds)')
    parser.add_argument(
        '--allow-duplicates',
        action='store_true',
        help='Allow more than one matching project for each package')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO if args.verbose else logging.WARNING,
        format='%(filename)s: %(message)s')

    rm = rmapi.CachedRMApi()

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
        # Project is ignored
        _, package = lineparts[:2]
        urls = set(lineparts[2:])

        logging.info('Next package: %s', package)
        # TODO: maybe load packages to skip dupes

        # Add canonical version of links
        urls.update({add_matching.canonicalize_url(url, strip_scheme=False) for url in urls})

        # Drop any plain download URLs (any canonical derivates are kept)
        urls = {url for url in urls if add_matching.is_valid_url(url)
                and not is_download_url(url)}
        if not urls:
            logging.info('No valid URLs given; skipping')
            continue

        # Look for matches in a particular ecosystem (later)
        # The ecosystem name isn't needed in order to look for unique projects, just the URL
        ecomatches = {add_matching.canonicalize_url(url, strip_scheme=False)
                      for url in urls
                      if add_matching.url_ecosystem(add_matching.canonicalize_url(url))}

        # Add index.html to URLs ending in slash
        urls.update({url + 'index.html' for url in urls if url.endswith('/')})
        # Add index.htm to URLs ending in slash
        urls.update({url + 'index.htm' for url in urls if url.endswith('/')})
        # Add trailing slash if not already present and not a .html URL
        urls.update({url + '/' for url in urls if not url.endswith('/')
                     and not url.endswith('.html') and not url.endswith('.htm')})
        # Swap http: and https: to provide another potential search
        urls.update({swap_scheme(url) for url in urls})
        # Add or remove www. to provide another potential search
        urls.update({swap_www(url) for url in urls})
        # Now, swap scheme of any new www URLs
        urls.update({swap_scheme(url) for url in urls})

        # Keep matches deduped by ID
        logging.debug('Checking these URLs: %s', ' '.join(urls))
        matches = {}
        for url in urls:
            # TODO: cache this
            projects = rm.find_project_by_ecosystem(url)
            for project in projects:
                logging.info('Found project %s', project['name'])
                matches[project['id']] = (project['name'], package, url)

        # Look for ecosystem matches
        # First, count the number of URLs case-insensitively
        ecourlcasematch = {u.lower() for u in ecomatches}
        if len(ecourlcasematch) > 1:
            logging.debug('Too many (%d) ecosystem URLs found: %s',
                          len(ecourlcasematch), ' '.join(u for u in ecomatches))

        elif len(ecourlcasematch) == 1:
            # Only one unique URL (case-insensitive) was found, but there might be more
            # than one URL just differing in case. Which one is the best one to use? No idea,
            # so choose one of the original ones at random.
            url = ecomatches.pop()
            eco_name = ecosystem_name(url)
            if eco_name:
                projects = rm.find_project_by_name(eco_name[0], eco_name[1])
                for project in projects:
                    logging.info('Found ecosystem project %s', project['name'])
                    matches[project['id']] = (project['name'], package, url)

        if len(matches) == 0:
            logging.info('Nothing found for package %s URL', package)
        elif len(matches) > 1 and not args.allow_duplicates:
            logging.info('Too many projects found for package %s', package)
            matches = {}

        for match in matches.values():
            print(' '.join(shlex.quote(m) for m in match))

        time.sleep(args.delay)


if __name__ == '__main__':
    main()
