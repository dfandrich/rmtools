"""Test check_latest_versions."""

import contextlib
import os
import tempfile
import time
import unittest
from unittest import mock

from rmtools import check_latest_versions


class TestPersistentVersions(unittest.TestCase):
    """Test PersistentVersions."""

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        # Replace XDG_DATA_HOME to prevent the user's versions file from being loaded
        self.env_patcher = mock.patch.dict(os.environ, {'XDG_DATA_HOME': self.tempdir})
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        self.addCleanup(self.cleanup_tempdir)

    def cleanup_tempdir(self):
        with contextlib.suppress(FileNotFoundError):
            os.unlink(os.path.join(self.tempdir, check_latest_versions.DATA_FILE))
        os.rmdir(self.tempdir)

    def test_persistent_dir(self):
        pv = check_latest_versions.PersistentVersions()
        self.assertEqual(pv.persistent_dir(), self.tempdir)

    def test_no_data_file(self):
        pv = check_latest_versions.PersistentVersions()
        pv.load()
        self.assertIs(pv.data, None)

    def test_save_load_data_file(self):
        pv = check_latest_versions.PersistentVersions()
        pv.load()
        # Abort if any data is found since that risks accidentally overwriting user data
        self.assertIs(pv.data, None)
        vers = {('pypi', 'pymodule', False): '1.2.3',
                ('https://example.com/xyzzy', 'xyzzy', True): '0'}
        pv.set_vers(vers)
        pv.save()
        del pv

        pv = check_latest_versions.PersistentVersions()
        pv.load()
        verdata = pv.get()
        assert verdata
        self.assertDictEqual(verdata.versions, vers)
        self.assertAlmostEqual(verdata.check_time, time.time(), delta=10)
