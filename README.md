# Release Monitoring Tools

This is a set of tools for interacting with the https://release-monitoring.org/
service (a.k.a. Anitya) that tracks software releases.

## Installation

Run this to install the program from the source tree:

    python3 -m pip install .

Run this to run the unit test suite:

    pytest

or

    python3 -m unittest

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

### add-matching

This program adds new packages to an existing project. Run it like:

```
add-matching --distro DistroName --token-file=~/.config/rmtools-token
```

Each line of input consists of space-separated project, package and URL strings
(each field can be single or double-quoted to embed a space).  If the project
doesn't already contain any package in the given distro, then
release-monitoring.org is searched for a project with the given project name
and homepage URL. If one is found, the given package is added to the project.
If not, the line is skipped and nothing is added.

This input data is generally available in distributions' package metadata. For
example, a simple way of generating it with an RPM-based distribution is with
a command like:

```sh
rpm -q --queryformat '%{NAME} %{NAME} %{URL}\n' -p SRPMS/*.src.rpm
```

However, often distributions will use a prefix on package names (e.g. `python-`
for Python modules or `perl-` for perl packages) so some post-processing may be
required to match the plain project names usually found in Anitya.

The `--token-file` option points to a file containing a
release-monitoring.org token, which can be generated at
https://release-monitoring.org/settings/

The program makes sure that nothing is added to a project without a firm match.
There are many projects in Anita with the same name but in different namespaces
(e.g. `curl` is the name of a C library, a Rust crate and a R package) so it
takes a match on another piece of metadata before a package is added. This
metadata is nominally the URL provided in the input, but if that doesn't
directly match the Anitya Homepage (with a bit of a fuzz factor), a deeper
check is needed. add-matching does not look for alternate project names.
Each package name that is added is written to stdout.

If the URL is for a known site that supplies additional metadata, that site is
contacted to retrieve it. For example, if the input data or the Anitya project
data contains a PyPi URL, PyPi will be contacted to retrieve its idea of the
project home page and source code repository URL. If one of those match, then
the project is considered to be the right one and that package is added. This
lookup process is NOT done recursively.

If the `--no-external-match` option is given, external sites are not contacted
to obtain more project information to help the match algorithm find the correct
Anitya project. This will not cause packages to be added to the incorrect
projects but could rather cause a package to be skipped due to an insufficient
match.

URLs given on the input are checked to see if they redirect, unless the
`--no-redirect-check` option is given (or `--no-external-match`). The
redirected location is matched just like the original URL.

Some projects appear more than once in Anitya. If such a duplicate is found,
the package is skipped since it's not clear which would be the preferred one.

If the `--dump-existing` option is given, a list is written to the given file
of all packages in Anitya for the given distribution. If used with
`--no-external-match`, it will only dump newly-added packages.

Some external sites (e.g. GitHub) may have rate limits on accessing the
metadata (these limits can be as low as one per minute averaged).  If you start
seeing rate limit errors from GitHub while performing bulk updates over many
packages, use the `--gh-token-file` option to specify a path to a file holding
a GitHub token in order to authenticate your GitHub API calls. The rate limit
for authenticated requests is several orders of magnitude larger than the
unauthenticated limit.

### find-project

This program searches for existing projects matching a package. Run it like:
```
find-project
```
Each line of input consists of space-separated project, package and URL strings
(each field can be double-quoted to embed a space).  The project field is
ignored, but something must be supplied in that first field for compatibility
with the input format of `add-matching`.

The output is in the same format, namely:
```
project package URL
```
with the matched information. This can be fed into `add-matching` to add these
packages to the given projects.  This shouldn't be done without first
double-checking the projects to ensure they are the correct ones. It often
happens that an umbrella URL (for an organization, for example) will be used for
many sub-projects in a site, so false positives can easily occur.

The `--allow-duplicates`` option will create entries for each matching project,
even if there is more than one. Normally, those with more than one match are
skipped entirely since there is no way to know which is the correct entry. Use
of this option is nearly guaranteed to find invalid entries, but can still be
useful to find more potential projects for manual verification.

## License

This program is Copyright © 2023–2025 by Daniel Fandrich. It is distributed
under the terms of the GNU General Public License as published by the Free
Software Foundation; either version 2 of the License, or (at your option) any
later version.
