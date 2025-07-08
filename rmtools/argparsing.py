"""Functions to use for argument parsing."""

import os


class ExpandUserFileName:
    """argparsing type that opens a file while expanding tildes.

    User directories with tildes (e.g. ~user/foo) are expanded first.

    Future improvements:
    - check if the file is the correct type (e.g. file vs directory)
    """

    def __init__(self, mode: str = 'r'):
        self.mode = mode

    def __call__(self, filename: str):
        fn = os.path.expanduser(filename)
        return open(fn, self.mode)
