import argparse
import os
import subprocess
import unittest

POSTPROCESS_SCRIPT = "script/bluray_to_mkv.py"  # Path to the post-processing script
POSTPROCESS_EXIT_CODE_SUCCESS = 93  # Returned code when post-process is successful

# NZBGet conveys a wealth of information to the post-processing script by using environment variables.
ENVAR_DOWNLOAD_DIRECTORY = "NZBPP_DIRECTORY"  # Directory path of downloaded files
ENVAR_DOWNLOAD_STATUS = "NZBPP_TOTALSTATUS"  # Status of downloaded files (e.g., success, failure)
ENVAR_MKV_DIRECTORY = "NZBPO_DIRECTORY"  # Directory path of converted movies


class MkvConversionTest(unittest.TestCase):
    def test_convert_bluray_to_mkv(self):
        # A Blu-Ray disc was downloaded, par-checked and unpacked successfully.
        os.environ[ENVAR_DOWNLOAD_STATUS] = "SUCCESS"

        # The post-processing script is called to convert the Blu-Ray disc.
        self.assertEqual(
            subprocess.call(["python", POSTPROCESS_SCRIPT]), POSTPROCESS_EXIT_CODE_SUCCESS,
            "The post-processing script did not return the SUCCESS status code.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Test the conversion of a Blu-Ray disc to MKV file.")
    parser.add_argument('test', nargs='*', help="test(s) to be executed")
    parser.add_argument('--src', required=True, help="source directory of Blu-Ray disc")
    parser.add_argument('--dst', required=True, help="destination directory for MKV file")
    args = parser.parse_args()

    os.environ[ENVAR_DOWNLOAD_DIRECTORY] = args.src
    os.environ[ENVAR_MKV_DIRECTORY] = args.dst

    unittest.main(argv=[parser.prog] + args.test)
