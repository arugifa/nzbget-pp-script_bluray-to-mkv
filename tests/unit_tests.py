from datetime import timedelta
import os
import sys
from pathlib import Path, PurePath
import subprocess
import unittest
import unittest.mock

sys.path.append(os.path.abspath('.'))
from script import bluray_to_mkv as script

FIXTURES_DIR = Path('tests/fixtures')


class ScriptTest(unittest.TestCase):
    @unittest.mock.patch('script.bluray_to_mkv.subprocess.check_output')
    def test_find_makemkvcon_binary(self, mock_subprocess_output):
        binary_path = PurePath('/usr/bin/makemkvcon')
        mock_subprocess_output.return_value = "{}\n".format(binary_path)

        self.assertEqual(script.find_makemkv_binary(), binary_path)

    @unittest.mock.patch('script.bluray_to_mkv.subprocess.check_output')
    def test_unable_to_find_makemkvcon_binary(self, mock_subprocess_output):
        mock_subprocess_output.side_effect = subprocess.CalledProcessError(returncode=1, cmd='which makemkvcon')

        self.assertEqual(script.find_makemkv_binary(), None)

    def test_script_configuration_options_must_be_defined(self):
        self.assertFalse(script.is_configured())  # No environment variable is yet defined

        for option in script.REQUIRED_OPTIONS:  # Set up environment variables
            os.environ[option] = str()

        self.assertTrue(script.is_configured())

        for option in script.REQUIRED_OPTIONS:  # Clean up environment variables
            os.environ.pop(option)

    def test_find_blu_ray_directories_in_downloaded_files(self):
        download_path = FIXTURES_DIR / 'downloads/blu_ray_discs_as_directories'
        discs = [download_path / 'movie' / 'disc_{}'.format(i) for i in range(1, 3)]

        for i in range(-1, 1):
            self.assertEqual(script.find_blu_ray_discs(download_path, disc_set=i), (None, list()))
        for i in range(1, 4):
            self.assertEqual(script.find_blu_ray_discs(download_path, disc_set=i), ("file", discs[:i]))

    def test_find_blu_ray_iso_images_in_downloaded_files(self):
        download_path = FIXTURES_DIR / 'downloads/blu_ray_discs_as_iso_images'
        discs = [download_path / 'movie' / 'disc_{}.iso'.format(i) for i in range(1, 3)]

        for i in range(-1, 1):
            self.assertEqual(script.find_blu_ray_discs(download_path, disc_set=i), (None, list()))
        for i in range(1, 4):
            self.assertEqual(script.find_blu_ray_discs(download_path, disc_set=i), ("iso", discs[:i]))

    @unittest.mock.patch('script.bluray_to_mkv.find_makemkv_binary')
    @unittest.mock.patch('script.bluray_to_mkv.subprocess.Popen')
    def test_identify_movie_titles_in_makemkvcon_output(self, mock_popen, mock_find_makemkv):
        # Initialization.
        makemkvcon_binary = PurePath('/usr/bin/makemkvcon')
        mock_find_makemkv.return_value = makemkvcon_binary

        disc = {'type': 'iso', 'path': PurePath('/downloads/movie.iso')}
        titles = [
            {'chapters': 16, 'duration': timedelta(0, 8074), 'mkv': 'MOVIE_t04.mkv', 'number': 4, 'size': 31.8},
            {'chapters': 4, 'duration': timedelta(0, 2488), 'mkv': 'MOVIE_t03.mkv', 'number': 3, 'size': 6.0},
            {'chapters': 2, 'duration': timedelta(0, 1408), 'mkv': 'MOVIE_t02.mkv', 'number': 2, 'size': 3.4},
            {'chapters': 2, 'duration': timedelta(0, 1080), 'mkv': 'MOVIE_t01.mkv', 'number': 1, 'size': 2.6},
            {'chapters': 2, 'duration': timedelta(0, 693), 'mkv': 'MOVIE_t00.mkv', 'number': 0, 'size': 1.6},
        ]

        makemkv_command = [makemkvcon_binary, '-r', 'info', '{type}:"{path}"'.format(**disc)]

        # Tests.
        for i in range(-1, 1):
            self.assertEqual(script.identify_movie_titles(disc, count=i), list())

        for i in range(1, 6):
            mock_find_makemkv.reset_mock()

            with (FIXTURES_DIR / 'makemkv' / 'makemkvcon_info_output.txt').open(buffering=1) as f:
                mock_popen.return_value.__enter__.return_value.stdout = f
                results = script.identify_movie_titles(disc, count=i)

            self.assertTrue(mock_find_makemkv.called)
            self.assertEqual(mock_popen.call_args[0][0], makemkv_command)
            self.assertEqual(results, titles[:i])

    @unittest.mock.patch('script.bluray_to_mkv.find_makemkv_binary')
    @unittest.mock.patch('script.bluray_to_mkv.subprocess.Popen')
    def test_convert_a_bluray_movie_title_to_mkv(self, mock_popen, mock_find_makemkv):
        # Initialization.
        movie = "Super Movie"
        disc = {'type': 'iso', 'path': PurePath('/downloads/movie.iso')}
        title = {'chapters': 16, 'duration': timedelta(0, 8074), 'mkv': 'MOVIE_t04.mkv', 'number': 4, 'size': 31.8}
        profile = PurePath('/home/user/.MakeMKV/makemkvcon.mmcp.xml')

        destination_directory = PurePath('/library/movies')
        mkv_name = '{0} - {1}.mkv'.format(movie, title['number'])
        mkv_path = destination_directory / mkv_name

        makemkv_binary = PurePath('/usr/bin/makemkvcon')
        mock_find_makemkv.return_value = makemkv_binary

        mock_destination_directory = unittest.mock.MagicMock()
        mock_destination_directory.__truediv__.return_value.with_name.return_value = mkv_path

        makemkv_command = [makemkv_binary, '--profile="{}"'.format(profile), 'mkv', '{type}:"{path}"'.format(**disc),
                           title['number'], mock_destination_directory]

        # Test.
        with (FIXTURES_DIR / 'makemkv' / 'makemkvcon_mkv_output.txt').open(buffering=1) as f:
            mock_popen.return_value.__enter__.return_value.stdout = f
            movie_mkv = script.convert_movie_to_mkv(movie, disc, title, mock_destination_directory, profile)

        # Test assertions.
        self.assertTrue(mock_find_makemkv.called)
        self.assertEqual(mock_popen.call_args[0][0], makemkv_command)
        mock_destination_directory.__truediv__.assert_called_once_with(title['mkv'])
        mock_destination_directory.__truediv__.return_value.with_name.assert_called_once_with(mkv_name)
        self.assertEqual(movie_mkv, mkv_path)


if __name__ == '__main__':
    unittest.main()
