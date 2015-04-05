import logging
import os
import sys
import pathlib
import subprocess
import unittest
import unittest.mock

sys.path.append(os.path.abspath('..'))
from script import bluray_to_mkv as script

FIXTURES_DIR = pathlib.Path('./test_fixtures')


class ScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script.log.addHandler(logging.NullHandler())

    @unittest.mock.patch('script.bluray_to_mkv.subprocess.check_output')
    def test_find_makemkv_binary(self, mock_subprocess_output):
        binary_path = pathlib.PurePath('/usr/bin', script.MAKEMKV_BINARY)
        mock_subprocess_output.return_value = '{}\n'.format(binary_path)

        self.assertEqual(script.find_makemkv_binary(), binary_path)
        mock_subprocess_output.assert_called_once_with(
            ['which', script.MAKEMKV_BINARY], stderr=subprocess.DEVNULL, universal_newlines=True)

    @unittest.mock.patch('script.bluray_to_mkv.subprocess.check_output')
    def test_makemkv_must_be_installed(self, mock_subprocess_output):
        command_line = ['which', script.MAKEMKV_BINARY]
        mock_subprocess_output.side_effect = subprocess.CalledProcessError(returncode=1, cmd=command_line)

        self.assertEqual(script.find_makemkv_binary(), None)
        mock_subprocess_output.assert_called_once_with(
            command_line, stderr=subprocess.DEVNULL, universal_newlines=True)

    def test_script_options_must_be_defined(self):
        # The script is not configured if no environment variable is defined.
        self.assertFalse(script.is_configured())

        # The script is configured if environment variables for script's options are defined.
        for option in script.REQUIRED_OPTIONS:
            os.environ[option] = str()

        self.assertTrue(script.is_configured())

        # Cleanup environment variables for next unit tests.
        for option in script.REQUIRED_OPTIONS:
            os.environ.pop(option)

    def test_find_blu_ray_directories_in_downloaded_files(self):
        download_path = FIXTURES_DIR / 'downloads/download_1'
        discs = [download_path / 'movie' / 'disc_{}'.format(i) for i in range(1, 3)]

        self.assertEqual(script.find_blu_ray_sources(download_path, multi=0), ("file", discs))
        self.assertEqual(script.find_blu_ray_sources(download_path, multi=1), ("file", discs[0]))

    def test_find_blu_ray_iso_images_in_downloaded_files(self):
        download_path = FIXTURES_DIR / 'downloads/download_2'
        discs = [download_path / 'movie' / 'disc_{}.iso'.format(i) for i in range(1, 3)]

        self.assertEqual(script.find_blu_ray_sources(download_path, multi=0), ("iso", discs))
        self.assertEqual(script.find_blu_ray_sources(download_path, multi=1), ("iso", discs[0]))
        self.assertEqual(script.find_blu_ray_sources(download_path, multi=2), ("iso", discs))

    @unittest.mock.patch('script.bluray_to_mkv.find_makemkv_binary')
    @unittest.mock.patch('script.bluray_to_mkv.subprocess.Popen')
    def test_identify_movie_titles_in_makemkvcon_output(self, mock_popen, mock_find_makemkv):
        source = {'type': 'iso', 'path': pathlib.PurePath('/downloads/movie.iso')}

        mock_find_makemkv.return_value = pathlib.PurePath('/usr/bin', script.MAKEMKV_BINARY)

        with (FIXTURES_DIR / 'makemkv' / 'makemkvcon_info_output.txt').open('r', buffering=1) as f:
            mock_popen.return_value.__enter__.return_value.stdout = f
            title = script.identify_movie_titles(source)

        mock_find_makemkv.assert_called_once_with()
        mock_popen.assert_called_once_with(
            [mock_find_makemkv.return_value, '-r', 'info', '{type}:{path}'.format(**source)],
            stderr=subprocess.STDOUT, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True)
        self.assertEqual(title, {'number': 4, 'fname': 'MOVIE_t04.mkv', 'chapters': 16, 'size': 31.8})

    @unittest.mock.patch('script.bluray_to_mkv.find_makemkv_binary')
    @unittest.mock.patch('script.bluray_to_mkv.subprocess.Popen')
    def test_convert_bluray_to_mkv(self, mock_popen, mock_find_makemkv):
        movie = "Super Movie"
        source = {'type': 'iso', 'path': pathlib.PurePath('/downloads/movie.iso')}
        title = {'number': 4, 'fname': 'MOVIE_t04.mkv', 'chapters': 16, 'size': 31.8}
        destination = pathlib.PurePath('/library/movies')
        profile = pathlib.PurePath('/home/user/.MakeMKV/makemkvcon.mmcp.xml')
        mkv_dst_path = destination / '{}.mkv'.format(movie)

        mock_find_makemkv.return_value = pathlib.PurePath('/usr/bin', script.MAKEMKV_BINARY)
        mock_popen.return_value.returncode = 0
        mock_destination = unittest.mock.MagicMock()
        mock_destination.__truediv__.return_value.with_name.return_value = mkv_dst_path

        with (FIXTURES_DIR / 'makemkv' / 'makemkvcon_mkv_output.txt').open('r', buffering=1) as f:
            mock_popen.return_value.stdout = f
            mkv_real_path = script.convert_to_mkv(movie, source, title, mock_destination, profile)

        self.assertEqual(mkv_real_path, mkv_dst_path)
        mock_find_makemkv.assert_called_once_with()
        mock_popen.assert_called_once_with(
            [mock_find_makemkv.return_value, '--profile={}'.format(profile),
             'mkv', '{type}:{path}'.format(**source), title['number'], mock_destination],
            stderr=subprocess.STDOUT, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True)
        mock_destination.__truediv__.assert_called_once_with(title['fname'])
        mock_destination.__truediv__.return_value.with_name.assert_called_once_with('{}.mkv'.format(movie))


if __name__ == '__main__':
    unittest.main()
