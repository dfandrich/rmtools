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

## Use

release-monitoring.org is a site that looks for updated versions of software
packages.  Its original use was for Linux (and other) distribution vendors to
know when a newer version of a package is available upstream so it can be
updated and brought to their users. Each distribution using the service has the
option of associating their packages with the release-monitoring.org (called
r-m from here on) ones (called "projects") to make it easy to track which of
their packages needs updating when a newer project is available.

The rmtools program `check-latest-versions` checks for newer packages contained
in a local list you specify and can be run periodically and used to generate an
e-mail or other notification when that happens.

The remaining programs are used to help bootstrap the mapping of distribution
packages to r-m projects so `check-latest-versions` (and anything else using
r-m) can find what you're looking for. This can be a tricky procedure because
there is no unique, universal identifier of all projects that can unambiguously
identify them in r-m. Instead, you need to rely on heuristics to avoid
associating a package with the wrong project. At every stage you should
manually perform spot checks on the input data to find bad data or incorrect
assumptions.

Here's is a suggested workflow for adding distro packages to r-m.

1. Use `metadata-parse` to generate a list of packages in the distro. If that
program won't handle your package manager, create the list some other way.

2. Use `add-matching` to associate the low-hanging fruit.  This program is
quite safe to run (i.e. it has a low likelihood of associating a package
with the wrong project). It relies on two bits of information supplied by you:
the r-m project name and its matching URL. If the provided URL matches the
project in r-m, the package is added to the project. The URLs in r-m are
generally quite specific, whereas the URLs used in some distributions might be
more generic (e.g. all Gnome applications might have the URL
https://www.gnome.org/). In such cases, the association will NOT be made to avoid
the possibility of a false association.

3. Run `add-matching` multiple times with manipulated URLs. To use the
Gnome example, if you know that all your packages with https://www.gnome.org/
as the URL are part of the Gnome project (as one would hope), and that the
package names are the same as the Gnome project's names, then the problem of
the URLs not matching can be solved by changing the URLs fed to `add-matching`.
Rather than using the URL used in the package, new ones can be synthesized to
match what's in r-m and to force a match. Many Gnome application packages
in r-m use a URL of the form https://wiki.gnome.org/Apps/<projectname> which
can be easily created with a shell script. This step can be effective when done
multiple times and on multiple subsets of similar packages. However, be
absolutely sure of the provenance of your packages since adding fake data can
easily create bad associations if done carelessly.

4. Run `add-matching` multiple times with manipulated project names.
`add-matching` will only check the project names you specify; it will not try
to search for similar names or try to find them using other methods. If the
given project name isn't what's used in r-m, then the association will fail.
Distros will often add a prefix to some types of packages (e.g. `python-` for
Python packages, `perl-` for Perl packages or `lib` for libraries) whereas r-m
generally does not use such prefixes. Removing such prefixes from the project
names fed to `add-matching` (but NOT from the package names) is likely to allow
it to find the correct project in r-m. Since the URL is still used for
matching, it's almost impossible for an association to be made to an unrelated
project this way.

5. After the obvious project associations have been made, there will likely
still be many projects in r-m found under non-obvious names, or at least names
that are different from those used in packages. `find-project` can help find
these projects by searching based on the URL.  It will search r-m for projects
listing those URLs as their homepages, as well as many related URLs (e.g. with
and with a leading "www.", with and without a trailing slash, with a trailing
"index.html" removed). This can result in many queries for each package which
is slow and inefficient, so this should be done only after as many associations
as possible have already been made by `add-matching`. The `--dump-existing`
option in `add-matching` will write a file containing all known packages for a
distribution already in r-m, which is useful for filtering only those packages
left to process.

This step isn't as safe as `add-matching` because there is only a single bit of
data being matched instead of two. You should carefully vet the output of this
program before using it to find cases where this would result in bad
associations. A common problem is finding a URL match on the umbrella homepage
for a project that produces several packages, but your distro only packages one
of them. This problem is reduced somewhat because `find-project` will skip by
default any cases where it finds more than one project matching a URL.

Once you've manually checked the output of `find-project` for problems, feed it
back into `add-matching` to actually make the package associations.

6. There will inevitably be projects in your distro that aren't yet in r-m, so
they will need to be newly created for r-m to track them. This can be
complicated since r-m needs much detailed information to be able to accurately
determine when new releases have been made for a project. `create-project` can
be used to automatically create a subset of these new projects for you. Try to
be thorough in finding existing projects before creating new ones to avoid
overwhelming r-m with duplicates.

When creating new projects, try to use a name that others (including those
using other distributions) would find makes sense. This is usually (but not
always) the name used by the upstream project and not necessarily the name used
in your distro. For example, prefixes like `python-` and `perl-` (and many
others) used in some distributions) are seldom found in r-m. Instead, projects
are separated by "ecosystems" and projects with the same name are disambiguated
through them. `create-project` has the `--strip-project-prefix` option to
automatically strip prefixes from package names to make more sensible project
names in some cases, but, as always, carefully check your input data before
mass creating projects.

7. Any remaining projects will likely need to be created manually at r-m. These
include those that require human knowledge and experience to determine what the
best URL and means are to to extract version updates. Use some discretion as
well. If an upstream package hasn't been updated in 15 years, it's probably not
going to ever see another update and isn't worth adding to r-m at all.

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

### metadata-parse

This program reads the output of `rpm -qi` (or similar, such as `urpmq -i` and
`dnf info`) for one or more packages and write the package name and URL, one
package per line, as a space-separated project, package and URL string (each
field can be single or double-quoted to embed a space). If the
`--strip-project-prefix` option is present, the given prefix, if any is found,
will be removed from the project field only.  Often distributions will use a
prefix on package names (e.g.  `python-` for Python modules or `perl-` for perl
packages) that aren't usually found in r-m projects, so this can help to
generate useful project names from package names.

This program generates output similar to generating it from RPM directly with:
```sh
rpm -q --queryformat '%{NAME} %{NAME} %{URL}\n' -p SRPMS/*.src.rpm
```
as long as no spaces are found in the fields.  This input data is generally
available in most distributions' package metadata and can usually be generated
fairly easily using a package manager query function.

This is the data format used by the other rmtools programs.

While this program is an easy way to generate data files for the rest of
rmtools, it is lacking; specifically, it's unable to determine the URL used by
the source data files.  For RPM-based distributions, that is available in the
.spec files. Some amount of scripting on those files, probably based on
`rpmspec -P`, could extract the URLs used for `Source:` and `Source0:` tags (as
well as the homepage URL) and provide much more useful information to the other
utilities.

### add-matching

This program adds new packages to an existing project. Run it like:

```sh
add-matching --distro DistroName --token-file=~/.config/rmtools-token
```

Each line of input consists of space-separated project, package and URL strings
(each field can be single or double-quoted to embed a space).  If the project
doesn't already contain any package in the given distro, then
release-monitoring.org is searched for a project with the given project name
and homepage URL. If one is found, the given package is added to the project.
If not, the line is skipped and nothing is added.

The `--token-file` option points to a file containing a
release-monitoring.org token, which can be generated at
https://release-monitoring.org/settings/

The program makes sure that nothing is added to a project without a firm match.
There are many projects in Anita with the same name but in different namespaces
(e.g. `curl` is the name of a C library, a Rust crate and a R package) so it
takes a match on another piece of metadata before a package is added. This
metadata is nominally the URL provided in the input, but if that doesn't
directly match the Anitya Homepage (with a bit of a fuzz factor), a deeper
check is needed. `add-matching` does not look for alternate project names.
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

### create-project

This program creates new projects. Run it like:
```
create-project --distro DistroName --token-file=~/.config/rmtools-token
```
Each line of input consists of space-separated project, package and URL
strings, with an optional second URL that, when found, points to the repository
to be checked for updates, in which case the first URL is used as the
homepage.  For an RPM-based distribution, the two URLs would correspond to the
"Url:" and "Source0:" fields. This is the standard input format used by most
rmtools programs.

Only certain known URLs are supported and any other project is skipped, since
the knowledge of how to properly check versions is only known for certain
hosting sites (see the list below). The existing release tags for the project
are checked to make sure that they follow a known mapping to version number.
If any tag can't be understood, an error message is output and the project
creation is skipped.

If `--strip-project-prefix` is given, that prefix, if found, will be removed
from the package name to make the project name. If this option is used more
than once, only the first one to match will be removed.

Some ecosystems require that the project name match the ecosystem name, so in
those cases the supplied project name is ignored.

Unless `--no-add-package` is provided, the package is added to the project once
it is created, using the SRPM name.

For each created project, the program outputs a line of the form:
```
project package URL
```
which the same format used by `add-matching` and `find-project`.

Be careful using this tool. Making a mistake currently means manual work by the
release-monitoring.org sysadmins to delete a project. Be sure the project name
that will be created is appropriate for Anitya and makes sense for most users
and that the project doesn't already exist under another name.

These are the project hosts for which creation is supported:

* crates.io
* github.com
* gitlab.com
* metacpan.org
* npmjs.com
* npmjs.org
* pypi.org
* rubygems.org
* sourceforge.net

## License

This program is Copyright © 2023–2025 by Daniel Fandrich. It is distributed
under the terms of the GNU General Public License as published by the Free
Software Foundation; either version 2 of the License, or (at your option) any
later version.
