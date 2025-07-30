"""Extract package metadata from RPM files.

Input is expected to be the output of "rpm -qi X" or similar.
"""

import argparse
import logging
import re
import shlex
import sys
from dataclasses import dataclass

from rmtools import add_matching

# Match the package name from a full SRPM name
PACKAGE_RE = re.compile(r'^(.*)(-[\w\.+~^]+-[\w\.]+\.(\w)+(\d+))(\.\w+)?\.src\.rpm$')


@dataclass
class ProjectData:
    """Holds all data needed to add a new project."""
    project: str = ''
    package: str = ''
    url: str = ''


def strip_prefixes(name: str, prefixes: list[str]) -> str:
    """Remove the first matching prefix from the list from the name."""
    for prefix in prefixes:
        stripped = name.removeprefix(prefix)
        if stripped != name:
            return stripped
    return name


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
        '--strip-project-prefix',
        nargs='*',
        default=[],
        help='Strip one of these prefixes from the package name to create the project name')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO if args.verbose else logging.WARNING,
        format='%(filename)s: %(message)s')

    def show_project():
        print(shlex.quote(project.project), shlex.quote(project.package), shlex.quote(project.url))

    # Read data in the form of "rpm -qi" output
    project = ProjectData()
    for l in sys.stdin:
        l = l.strip()
        if ':' in l:
            key, value = l.split(':', 1)
            key = key.strip()
            value = value.strip()

            if key == 'Name':
                if project.project:
                    if project.url and project.package:
                        show_project()
                    else:
                        logging.info('Missing URL or package for %s', project.project)

                    project = ProjectData()
                project.project = strip_prefixes(value, args.strip_project_prefix)

            elif key == 'URL':
                if not project.project:
                    logging.error('Missing name before %s', key)
                    continue
                project.url = add_matching.canonicalize_url(value, strip_scheme=False)

            elif key in frozenset({'Source RPM', 'Source'}):
                if not project.project:
                    logging.error('Missing name before %s', key)
                    continue
                if not (p := PACKAGE_RE.search(value)):
                    logging.error('Bad SRPM %s for %s', value, project.project)
                    return
                project.package = p.group(1)

    if project.project:
        if project.url and project.package:
            show_project()
        else:
            logging.info('Missing URL or package for %s', project.project)


if __name__ == '__main__':
    main()
