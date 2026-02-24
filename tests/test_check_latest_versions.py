"""Test check_latest_versions."""

import contextlib
import os
import tempfile
import textwrap
import time
import unittest
from unittest import mock

from rmtools import check_latest_versions


class TestLoadConfig(unittest.TestCase):
    """Test load_config."""

    def test_load_config_xdg(self):
        content = textwrap.dedent("""
            check_packages:
              Distro:
              - pkg1
        """)
        with (mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': '/some/unique/path'}),
              mock.patch('builtins.open', mock.mock_open(read_data=content)) as mock_file):
            self.assertDictEqual(check_latest_versions.load_config(),
                                 {'check_packages': {'Distro': ['pkg1']}})
            mock_file.assert_called_with('/some/unique/path/rmcheck.yaml')

    def test_load_config_home(self):
        content = textwrap.dedent("""
            check_packages:
              Distro:
              - pkg1
        """)
        with (mock.patch.dict(os.environ, {'HOME': '/not/a/real/homedir'}, clear=True),
              mock.patch('builtins.open', mock.mock_open(read_data=content)) as mock_file):
            self.assertDictEqual(check_latest_versions.load_config(),
                                 {'check_packages': {'Distro': ['pkg1']}})
            mock_file.assert_called_with('/not/a/real/homedir/.config/rmcheck.yaml')

    def test_load_config_none(self):
        with mock.patch.dict(os.environ, clear=True):
            self.assertIsNone(check_latest_versions.load_config())


class TestPersistentVersions(unittest.TestCase):
    """Test PersistentVersions."""

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        # Replace XDG_DATA_HOME to prevent the user's config file from being loaded
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

    @mock.patch.dict(os.environ, {'HOME': '/a/very/strange/path'}, clear=True)
    def test_persistent_dir_home(self):
        pv = check_latest_versions.PersistentVersions()
        self.assertEqual(pv.persistent_dir(), '/a/very/strange/path/.local/share')

    @mock.patch.dict(os.environ, clear=True)
    def test_persistent_dir_default(self):
        pv = check_latest_versions.PersistentVersions()
        self.assertEqual(pv.persistent_dir(), '.')

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


class TestMakeKey(unittest.TestCase):
    """Test make_key."""

    def test_make_key(self):
        self.assertNotEqual(
            check_latest_versions.make_key(
                check_latest_versions.Ver('eco', 'proj', '0.0', False),
            ),
            check_latest_versions.make_key(
                check_latest_versions.Ver('eco1', 'proj', '0.0', False)
            )
        )
        self.assertNotEqual(
            check_latest_versions.make_key(
                check_latest_versions.Ver('eco', 'proj', '123', False),
            ),
            check_latest_versions.make_key(
                check_latest_versions.Ver('eco', 'proj_', '123', False)
            )
        )
        self.assertNotEqual(
            check_latest_versions.make_key(
                check_latest_versions.Ver('eco', 'proj', 'a', False),
            ),
            check_latest_versions.make_key(
                check_latest_versions.Ver('eco', 'proj', 'a', True)
            )
        )

    def test_make_key_nonunique(self):
        # Key is not based on the version
        self.assertEqual(
            check_latest_versions.make_key(
                check_latest_versions.Ver('eco', 'proj', '1.0', False),
            ),
            check_latest_versions.make_key(
                check_latest_versions.Ver('eco', 'proj', '999', False)
            )
        )
