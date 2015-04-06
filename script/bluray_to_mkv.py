#!/usr/bin/env python

###############################################################
### NZBGET POST-PROCESSING SCRIPT                           ###

# Convert a Blu-Ray to MKV.
#
# This script converts a Blu-Ray disc to MKV file with MakeMKV.
# Blu-Ray ISOs and directories can be processed.


###############################################################
### OPTIONS                                                 ###

#Directory=${MainDir}/mkv

### NZBGET POST-PROCESSING SCRIPT                           ###
###############################################################

from datetime import timedelta
import logging
import os
import pathlib
import re
import subprocess
import sys

# NZBGet conveys a wealth of information to the post-processing script by using environment variables.
ENVAR_DOWNLOAD_DIRECTORY = "NZBPP_DIRECTORY"  # Directory path of downloaded files
ENVAR_DOWNLOAD_STATUS = "NZBPP_TOTALSTATUS"  # Status of downloaded files (e.g., success, failure)
ENVAR_MAKEMKV_PROFILE = "NZBPO_PROFILE"  # Path of MakeMKV XML profile
ENVAR_MKV_DIRECTORY = "NZBPO_DIRECTORY"  # Directory path of converted movies
ENVAR_MOVIE_TITLES = "NZBPP_TITLES"
MAKEMKV_BINARY = "makemkvcon"
MAKEMKV_OUTPUT_CONVERSION_SUCCESS = 'Copy complete. 1 titles saved.'
MAKEMKV_PATTERN_TITLE = 'TINFO:(?P<title>\d+),{id},\d+,"(?P<info>{pattern})"'
MAKEMKV_PATTERN_TITLE_CHAPTERS = MAKEMKV_PATTERN_TITLE.format(id=8, pattern='(?P<chapters>\d+)')
MAKEMKV_PATTERN_TITLE_DURATION = MAKEMKV_PATTERN_TITLE.format(
    id=9, pattern='(?P<duration>(?P<hours>\d):(?P<minutes>\d{2}):(?P<seconds>\d{2}))')
MAKEMKV_PATTERN_TITLE_SIZE = MAKEMKV_PATTERN_TITLE.format(id=10, pattern='(?P<size>\d{1,2}.\d+ GB)')
MAKEMKV_PATTERN_TITLE_MKV = MAKEMKV_PATTERN_TITLE.format(id=27, pattern='(?P<mkv>.*\.mkv)')
MSG_END_CONVERSION = "Successfully converted {} to MKV."
NZBGET_LOG_FORMAT = "[%(levelname)s] %(message)s"
POSTPROCESS_EXIT_CODE_ERROR = 94
POSTPROCESS_EXIT_CODE_SUCCESS = 93  # Returned code when post-process is successful

REQUIRED_OPTIONS = (ENVAR_MAKEMKV_PROFILE, ENVAR_MKV_DIRECTORY)

# Logging configuration.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
logging.addLevelName(logging.DEBUG, "DETAIL")  # NZBGet prefix for DEBUG messages


def is_configured():
    """Verify that script configuration options are defined.

    :return: ``True`` if all options are defined; ``False`` otherwise.
    """
    missing_option = False
    for option in REQUIRED_OPTIONS:
        if option not in os.environ:
            logger.error("Unable to start Blu-Ray to MKV conversion. "
                         "The following configuration option must be defined: {}.".format(option))
            missing_option = True
    if missing_option:
        return False
    return True


def find_makemkv_binary():
    """Search for the binary of MakeMKV command line tool.

    :return: a ``PurePath`` object pointing to the MakeMKV binary, if this latter is found; ``None`` otherwise.
    """
    try:
        binary_path = subprocess.check_output(
            ['which', MAKEMKV_BINARY], stderr=subprocess.DEVNULL, universal_newlines=True)
    except subprocess.CalledProcessError:
        logger.error("MakeMKV binary not found.")
        return None
    return pathlib.PurePath(binary_path.rstrip())


def find_blu_ray_discs(path, disc_set=1):
    """Search for Blu-Ray discs in a directory.

    Blu-Ray discs can be stored either as subdirectories or iso images.

    :param path: directory where to perform the search.
    :param disc_set: number of discs to return among all the discs found.

    :return: a tuple in the form (disc types, discs found). The disc type is either "file" or "iso".
             The discs found are a list of ``Path`` objects and are sorted by name for "file" type,
             or in descending order of size for "iso" type.
    """
    disc_type = None
    if disc_set <= 0:
        return disc_type, list()

    path = pathlib.Path(path)
    discs = sorted(path.rglob('BDMV/index.bdmv'))
    if discs:
        disc_type = "file"
        for i in range(len(discs)):
            discs[i] = discs[i].parents[1]  # Keep root directory of the disc
    else:
        iso_images = path.rglob('*.iso')
        # Bigger discs are given more importance.
        discs = sorted(iso_images, key=lambda iso: iso.stat().st_size, reverse=True)
        if discs:
            disc_type = "iso"

    if discs:
        logger.debug("{0} discs were found in {1}".format(len(discs), path))
        discs = discs[:disc_set]

    return disc_type, discs


def identify_movie_titles(disc, count=1):
    """Browse through a Blu-Ray disc and look at the movie titles.

    As a disc can contain several movie titles and additional features, this function does its utmost
    to return the most relevant titles. If there is any doubt, no title is returned.

    :param disc: path of Blu-Ray disc to analyze.
    :param count: number of titles to extract from the disc.

    :return: a ``list`` of titles, sorted in descending order of duration. Each title is a ``dictionary`` with:
             - a number of ``chapters``,
             - a ``duration`` (``timedelta`` object),
             - a ``size`` in GB,
             - a ``mkv`` file name (used by MakeMKV during the conversion process).
    """
    titles = list()
    if count <= 0:
        return titles

    # List of regular expressions to match for retrieving titles information.
    # Each regex is associated to a conversion function.
    regexs = sorted([
        {
            'name': 'chapters',
            'pattern': re.compile(MAKEMKV_PATTERN_TITLE_CHAPTERS),
            'converter': lambda m: int(m.group('chapters')),
        },
        {
            'name': 'duration',
            'pattern': re.compile(MAKEMKV_PATTERN_TITLE_DURATION),
            'converter': lambda m: timedelta(**{unit: int(m.group(unit)) for unit in ('hours', 'minutes', 'seconds')}),
        },
        {
            'name': 'size',
            'pattern': re.compile(MAKEMKV_PATTERN_TITLE_SIZE),
            'converter': lambda m: float(m.group('size').split()[0]),
        },
        {
            'name': 'mkv',
            'pattern': re.compile(MAKEMKV_PATTERN_TITLE_MKV),
            'converter': lambda m: m.group('mkv'),
        },
    ], key=lambda regex: int(regex['pattern'].pattern.split(',')[1]))  # Sorting on MakeMKV INFO ID

    makemkv = [find_makemkv_binary(), '-r', 'info', '{type}:"{path}"'.format(**disc)]
    with subprocess.Popen(
            makemkv, stderr=subprocess.STDOUT,  stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        title = dict()
        line = p.stdout.readline()
        while line:
            for regex in regexs:
                while line:
                    line = line.rstrip()
                    match = regex['pattern'].match(line)
                    if match is not None:
                        title[regex['name']] = regex['converter'](match)
                        if regex['name'] == regexs[-1]['name']:
                            title['number'] = int(match.group('title'))
                            titles.append(title)
                            title = dict()
                        break
                    line = p.stdout.readline()
            line = p.stdout.readline()

    # Longer titles are given more importance.
    titles = sorted(titles, key=lambda title: title['duration'], reverse=True)
    for i in range(1, len(titles)):
        # Sometimes, several movie titles co-exist, with same duration/number of chapters but different audio tracks.
        if (titles[i]['duration'] == titles[i-1]['duration']) and (titles[i]['chapters'] == titles[i-1]['chapters']):
            logger.warning("Identical movie titles were found for {}".format(disc['path']))
            titles = list()
            break
    else:
        titles = titles[:count]

    return titles


def convert_movie_to_mkv(movie, disc, title, destination_directory, makemkv_profile):
    """Extract a movie title from a Blu-Ray disc and convert it into a MKV file.

    :param movie: name of the movie.
    :param disc: Blu-Ray disc containing the movie. A ``dictionary`` with the disc ``type`` and ``path``.
    :param title: movie title to convert. A ``dictionary`` with the ``number`` and ``mkv`` file name that MakeMKV uses
                  internally to identifies the title.
    :param destination_directory: path of the directory where the MKV file will be saved.
    :param makemkv_profile: a MakeMKV profile to use for the conversion.

    :return: path of the newly created MKV file.
    """
    makemkv = [find_makemkv_binary(), '--profile="{}"'.format(makemkv_profile), 'mkv', '{type}:"{path}"'.format(**disc),
               title['number'], destination_directory]

    conversion_status = None
    with subprocess.Popen(
            makemkv, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        line = last_line = p.stdout.readline()
        while line:
            line = line.rstrip()
            last_line = line
            logger.debug(line)
            line = p.stdout.readline()
        else:
            # Even when MakeMKV encounters an error, its status code is often set to 0.
            # That's why we use the last output line to check the conversion status.
            conversion_status = last_line

    mkv = destination_directory / title['mkv']
    if conversion_status != MAKEMKV_OUTPUT_CONVERSION_SUCCESS:
        try:
            mkv.unlink()
        except OSError:
            pass
        logger.error("Unable to convert the title {0} from disc {1}".format(title['number'], disc['path']))
        return None

    mkv_target = mkv.with_name('{0} - {1}.mkv'.format(movie, title['number']))
    try:
        mkv.rename(mkv_target)
    except OSError:
        logger.warning("Unable to rename {}".format(mkv))
    else:
        mkv = mkv_target

    return mkv


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    console.setFormatter(NZBGET_LOG_FORMAT)
    logger.addHandler(console)

    if is_configured() is False:
        sys.exit(POSTPROCESS_EXIT_CODE_ERROR)
