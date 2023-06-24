"""Notifies when newer versions of upstream packages are available
"""

import datetime
import logging
import os
import pickle
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from rmtools import rmapi

import yaml


CONFIG_FILE = 'rmcheck.yaml'
DATA_FILE = 'rmversions'


@dataclass
class Ver:
    "Holds a project version"
    ecosystem: str
    project: str
    version: str
    unstable: bool


class PersistentVersions:
    """Class to handle persisting the versions across runs"""

    @dataclass
    class PersistentVersionsData:
        "Version numbers to persist to check next time"
        config_ver: int  # always 1 (for now)
        check_time: float
        versions: Dict[Tuple, str]

    def __init__(self):
        self.data = None  # type: Optional[self.PersistentVersionsData]

    def set_vers(self, vers_dict: Dict[Tuple, str]):
        """Set new versions to persist"""
        self.data = self.PersistentVersionsData(1, datetime.datetime.now().timestamp(), vers_dict)

    def get(self) -> Optional[PersistentVersionsData]:
        return self.data

    def persistent_dir(self):
        """Get the directory in which to store the persistent version file"""
        if 'XDG_DATA_HOME' in os.environ:
            return os.environ['XDG_DATA_HOME']
        if 'HOME' in os.environ:
            return os.path.join(os.environ['HOME'], '.local', 'share')
        return '.'

    def load(self):
        """Load the persistent version file from disk"""
        try:
            with open(os.path.join(self.persistent_dir(), DATA_FILE), 'rb') as f:
                self.data = pickle.load(f)
        except FileNotFoundError:
            logging.warning("Previous version file not found; first run?")

    def save(self):
        """Save the versions in a file to load in later"""
        with open(os.path.join(self.persistent_dir(), DATA_FILE), 'wb') as f:
            pickle.dump(self.data, f, protocol=4)



def load_config() -> Optional[Dict[str, Any]]:
    """Load the program configuration file"""

    def load_config_file(fn: str) -> Dict[str, Any]:
        """Load the config file at the given path"""
        with open(fn) as f:
            return yaml.load(f, Loader=yaml.SafeLoader)

    if 'XDG_CONFIG_HOME' in os.environ:
        try:
            return load_config_file(os.path.join(os.environ['XDG_CONFIG_HOME'], CONFIG_FILE))
        except (FileNotFoundError, PermissionError):
            pass

    if 'HOME' in os.environ:
        try:
            return load_config_file(os.path.join(os.environ['HOME'], '.config', CONFIG_FILE))
        except (FileNotFoundError, PermissionError):
            pass

    return None


def check_packages(rm: rmapi.RMApi, packages: Dict[str, List[str]], unstable: bool) -> List[Ver]:
    """Check all the package versions at release-monitoring.org"""
    vers = []
    for distro in packages:
        for package in packages[distro]:
            logging.info('Retrieving version for %s', package)
            try:
                info = rm.get_distro_package_info(distro, package)
            except:
                logging.error('Error retrieving package info for "%s" in distro "%s"',
                              package, distro, exc_info=True)
            else:
                if info:
                    ver = info['version' if unstable else 'stable_version']
                    vers.append(Ver(info['ecosystem'], info['project'], ver, unstable))
                else:
                    logging.warning('Package not found for "%s" in distro "%s"', package, distro)
    return vers


def make_key(ver: Ver) -> Tuple:
    """Make a unique hashable key of the project at r-m.o"""
    return (ver.ecosystem, ver.project, ver.unstable)


def notify_new_ver(vers: List[Ver]):
    """Display a message listing all the updated versions"""
    for ver in vers:
        print(f'Project {ver.project} (at {ver.ecosystem}) has updated its version to '
              '{ver.version}')


def check_latest_versions(argv: List[str]):
    """Read the config file and check for updated project versions"""
    if len(argv) > 1 and argv[1] == '-v':
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(format='%(filename)s: %(message)s', level=level)

    conf = load_config()
    if not conf:
        logging.fatal('Configuration file could not be read')
        return 1

    if 'check_packages' not in conf and 'check_packages_unstable' not in conf:
        logging.fatal('No packages have been configured')
        return 1

    persist = PersistentVersions()
    persist.load()
    previous = persist.get()
    if previous:
        if previous.config_ver != 1:
            logging.error('Persist file is from a newer version; delete it to continue')
            return 2
        prev_date = datetime.datetime.fromtimestamp(previous.check_time)
        delta = datetime.datetime.now() - prev_date
        logging.info('Last check was at %s (%d hours ago)',
                     datetime.datetime.ctime(prev_date), delta.total_seconds() / 3600)

    rm = rmapi.RMApi()
    if 'check_packages' in conf:
        vers = check_packages(rm, conf['check_packages'], False)

    allvers = vers

    if 'check_packages_unstable' in conf:
        vers = check_packages(rm, conf['check_packages_unstable'], True)
        allvers.extend(vers)

    vers_dict = {make_key(ver): ver.version for ver in allvers}
    if previous:
        new_ver = []
        # Compare new versions to old ones
        for ver in allvers:
            key = make_key(ver)
            if key in previous.versions:
                if previous.versions[key] != ver.version:
                    logging.warning('New version found for %s (at %s): %s -> %s',
                                    ver.project, ver.ecosystem,
                                    previous.versions[key], ver.version)
                    new_ver.append(ver)
            else:
                logging.info('New package: %s (at %s)',
                             ver.project, ver.ecosystem)

        notify_new_ver(new_ver)
    else:
        logging.warning('First time running; initializing package versions')

    persist.set_vers(vers_dict)
    persist.save()


def main():
    sys.exit(check_latest_versions(sys.argv))


if __name__ == '__main__':
    main()
