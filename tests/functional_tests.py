import argparse
import os
import sys
import subprocess
import unittest

sys.path.append(os.path.abspath('.'))
from script.bluray_to_mkv import (
    ENVAR_DOWNLOAD_DIRECTORY,
    ENVAR_DOWNLOAD_STATUS,
    ENVAR_MAKEMKV_PROFILE,
    ENVAR_MKV_DIRECTORY,
    MSG_END_CONVERSION,
    POSTPROCESS_EXIT_CODE_ERROR,
    POSTPROCESS_EXIT_CODE_SUCCESS,
)

NZBGET_OPTIONS = [ENVAR_DOWNLOAD_DIRECTORY, ENVAR_DOWNLOAD_STATUS]
SCRIPT_OPTIONS = [ENVAR_MAKEMKV_PROFILE, ENVAR_MKV_DIRECTORY]
ENVIRONMENT_VARS = NZBGET_OPTIONS + SCRIPT_OPTIONS

POSTPROCESS_SCRIPT = "script/bluray_to_mkv.py"  # Path to the post-processing script


class BluRayToMkvTest(unittest.TestCase):
    def tearDown(self):
        for var in ENVIRONMENT_VARS:
            os.environ.pop(var, None)

    def test_script_fails_if_options_are_not_defined(self):
        self.assertEqual(
            subprocess.call(['python', POSTPROCESS_SCRIPT], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL),
            POSTPROCESS_EXIT_CODE_ERROR, "The post-processing script did not return the ERROR status code.")

    def test_convert_a_bluray_to_mkv(self):
        # A Blu-Ray disc was downloaded, par-checked and unpacked successfully.
        self.assertTrue(
            os.path.isdir(os.environ[ENVAR_DOWNLOAD_DIRECTORY]), "The download directory does not exist.")
        download_name = os.path.basename(os.environ[ENVAR_DOWNLOAD_DIRECTORY])
        os.environ[ENVAR_DOWNLOAD_STATUS] = "SUCCESS"

        # The post-processing script is called to convert the Blu-Ray disc.
        self.assertTrue(os.path.isfile(os.environ[ENVAR_MAKEMKV_PROFILE]), "The MakeMKV profile does not exist.")

        pp_script = subprocess.Popen(['python', POSTPROCESS_SCRIPT], stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(
            pp_script.communicate()[0].rstrip(), MSG_END_CONVERSION.format(download_name),
            "Something went wrong during the conversion process. Please check output of the script.")
        self.assertEqual(
            pp_script.returncode, POSTPROCESS_EXIT_CODE_SUCCESS,
            "The post-processing script did not return the SUCCESS status code.")

        # The Blu-Ray disc was converted to a MKV file.
        mkv_fname = "{}.mkv".format(download_name)
        mkv_fpath = os.path.join(os.environ[ENVAR_MKV_DIRECTORY], mkv_fname)
        self.assertTrue(os.path.isfile(mkv_fpath), "The conversion failed: no MKV file has been found.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Test the conversion of a Blu-Ray disc to MKV file.")
    parser.add_argument('test', nargs='*', help="test(s) to be executed")
    parser.add_argument('--source', required=True, help="source directory of Blu-Ray disc")
    parser.add_argument('--destination', required=True, help="destination directory for MKV file")
    parser.add_argument('--profile', required=True, help="path of MakeMKV profile")
    args = parser.parse_args()

    os.environ[ENVAR_DOWNLOAD_DIRECTORY] = args.source
    os.environ[ENVAR_MKV_DIRECTORY] = args.destination
    os.environ[ENVAR_MAKEMKV_PROFILE] = args.profile

    unittest.main(argv=[parser.prog] + args.test)
