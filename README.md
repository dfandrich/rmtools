# Release Monitoring Tools

This is a set of tools for interacting with the https://release-monitoring.org/
service (a.k.a. Anitya) that tracks software releases.

## Installation

Run this to install the program from the source tree:

    python3 -m pip install .

## Programs

### check-latest-versions

This program checks release-monitoring.org for updates versions of one or more
packages.  The package names given to check are the ones used by the specified
distribution, which isn't necessarily the same as the upstream project. They
are only used to find the correct release-monitoring.org ID, since names are
much easier to work with than arbitrary numbers.

Create a file `$HOME/.config/rmcheck.yaml` that contains the list of packages
to check. The format looks like:

```
check_packages:
  MacPorts:
  - gpatch
  Mageia:
  - pngtools
  - stella
check_packages_unstable:
  NixOS:
  - gnumake
  Mageia:
  - python3-yaml
```

Entries under `check_packages` and `check_packages_unstable` are the disto
names for which packages are to be checked. Under each disto list the packages
*as used in that distro*. These will be used to look up the project name at
release-monitoring.org and the version thereof. The packages under
`check_packages_unstable` will have their prerelease versions checked (instead
to their stable versions). Not all projects use prerelease versions.

On the first run, the initial package versions are read and stored in
`$HOME/.local/share/rmversions`. On subsequent runs, any changed versions will
be written to stdout. If set up as a cron job, the output can be mailed to you
automatically (see your cron documentation to find out how). If the `-v` option
is given, verbose logging is enabled.

## License

This program is Copyright © 2023–2025 by Daniel Fandrich. It is distributed
under the terms of the GNU General Public License as published by the Free
Software Foundation; either version 2 of the License, or (at your option) any
later version.
