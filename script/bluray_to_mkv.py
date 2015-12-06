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

import argparse
from datetime import timedelta
import logging
import os
from pathlib import Path, PurePath
import re
import subprocess
import sys

# NZBGet conveys a wealth of information to the post-processing script by using environment variables.
ENVAR_DOWNLOAD_DIRECTORY = "NZBPP_DIRECTORY"  # Directory path of downloaded files
ENVAR_DOWNLOAD_NAME = "NZBPP_NZBNAME"
ENVAR_DOWNLOAD_STATUS = "NZBPP_TOTALSTATUS"  # Status of downloaded files (e.g., success, failure)
ENVAR_MAKEMKV_PROFILE = "NZBPO_PROFILE"  # Path of MakeMKV XML profile
ENVAR_MKV_DESTINATION = "NZBPO_DESTINATION"  # Directory path of converted movies
ENVAR_MOVIE_TITLES = "NZBPP_TITLES"
MAKEMKV_BINARY = "makemkvcon"
MAKEMKV_OUTPUT_CONVERSION_SUCCESS = 'Copy complete. 1 titles saved.'
#[DETAIL] Operation successfully completed
#[DETAIL] Copy complete. 1 titles saved.
MAKEMKV_OUTPUT_ILLEGAL_INSTRUCTION = 'Illegal instruction.'
MAKEMKV_PATTERN_TITLE = 'TINFO:(?P<title>\d+),{id},\d+,"(?P<info>{pattern})"'
MAKEMKV_PATTERN_TITLE_CHAPTERS = MAKEMKV_PATTERN_TITLE.format(id=8, pattern='(?P<chapters>\d+)')
MAKEMKV_PATTERN_TITLE_DURATION = MAKEMKV_PATTERN_TITLE.format(
    id=9, pattern='(?P<duration>(?P<hours>\d):(?P<minutes>\d{2}):(?P<seconds>\d{2}))')
MAKEMKV_PATTERN_TITLE_SIZE = MAKEMKV_PATTERN_TITLE.format(id=10, pattern='(?P<size>\d{1,}.\d+ \w?B)')
MAKEMKV_PATTERN_TITLE_MKV = MAKEMKV_PATTERN_TITLE.format(id=27, pattern='(?P<mkv>.*\.mkv)')
MSG_END_CONVERSION = "Successfully converted {} to MKV."
NZBGET_LOG_FORMAT = "[%(levelname)s] %(message)s"
POSTPROCESS_EXIT_CODE_ERROR = 94
POSTPROCESS_EXIT_CODE_SUCCESS = 93  # Returned code when post-process is successful

REQUIRED_OPTIONS = (ENVAR_MAKEMKV_PROFILE, ENVAR_MKV_DESTINATION)

# Logging configuration.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
logging.addLevelName(logging.DEBUG, "DETAIL")  # NZBGet prefix for DEBUG messages


def nzbget_is_configured():
    """Verify that the script configuration options are defined.

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
    return PurePath(binary_path.rstrip())


def find_blu_ray_discs(path, disc_set=0):
    """Search for Blu-Ray discs in a directory.

    Blu-Ray discs can be stored either as subdirectories or iso images.

    :param path: directory where to perform the search.
    :param disc_set: number of discs to return among all the discs found. Defaults to ``1``.

    :return: a tuple in the form (disc type, discs found). The disc type is either "file" or "iso".
             The discs found are a list of ``Path`` objects and are sorted by name for "file" type,
             or in descending order of size for "iso" type.
    """
    disc_type = None
    if disc_set < 0:
        return disc_type, list()

    path = Path(path)
    discs = sorted([disc for disc in path.rglob('BDMV/index.bdmv') if disc.is_file()])
    if discs:
        disc_type = "file"
        for i in range(len(discs)):
            discs[i] = discs[i].parents[1]  # Keep root directory of the disc
    else:
        iso_images = [image for image in path.rglob('*.iso') if image.is_file()]
        # Bigger discs are given more importance.
        discs = sorted(iso_images, key=lambda iso: iso.stat().st_size, reverse=True)
        if discs:
            disc_type = "iso"

    discs_found = len(discs)
    if disc_set:
        discs = discs[:disc_set]
    logger.info("{0} Blu-Ray discs selected among {1} found in \"{2}\"".format(len(discs), discs_found, path))

    return disc_type, discs


def identify_movie_titles(disc, count=10):
    """Browse through a Blu-Ray disc and look at the movie titles.

    As a disc can contain several movie titles and additional features, this function does its utmost
    to return the most relevant titles. If there is any doubt, no title is returned.

    :param disc: path of Blu-Ray disc to analyze. A ``dictionary`` with ``type`` and ``path`` of the disc.
    :param count: number of titles to extract (only metadata) from the disc.

    :return: a ``list`` of titles, sorted in descending order of duration. Each title is a ``dictionary`` with:
             - a number of ``chapters``,
             - a ``duration`` (``timedelta`` object),
             - a ``size`` in GB,
             - a ``mkv`` file name (used by MakeMKV during the conversion process).
    """
    titles = list()
    if count < 0:
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
            'converter': lambda m: float(m.group('size').split()[0]) if 'GB' in m.group('size') else None,
        },
        {
            'name': 'mkv',
            'pattern': re.compile(MAKEMKV_PATTERN_TITLE_MKV),
            'converter': lambda m: m.group('mkv'),
        },
    ], key=lambda regex: int(regex['pattern'].pattern.split(',')[1]))  # Sorting on MakeMKV INFO ID

    makemkv = [str(find_makemkv_binary()), '-r', 'info', '{type}:{path}'.format(**disc)]
    with subprocess.Popen(
            makemkv, stderr=subprocess.STDOUT,  stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        title = dict()
        line = p.stdout.readline()
        while line:
            for regex in regexs:
                while line:
                    line = line.rstrip()
                    match = regex['pattern'].match(line)
                    if match:
                        title[regex['name']] = regex['converter'](match)
                        if regex['name'] == regexs[-1]['name']:
                            title['number'] = int(match.group('title'))
                            for info in title.values():
                                if info is None:
                                    break
                            else:
                                titles.append(title)
                            title = dict()
                        break
                    line = p.stdout.readline()
            line = p.stdout.readline()

    # Movie titles are likely to be the longest/biggest titles.
    titles = sorted(titles, key=lambda title: (title['duration'], title['size']), reverse=True)
    movie_titles = [titles[0]] if titles else list()
    for i in range(1, len(titles)):
        if count and (titles[i]['duration'] == titles[i-1]['duration']) and (titles[i]['size'] == titles[i-1]['size']):
            # Sometimes, several movie titles co-exist, with same duration but different audio tracks.
            # In this case, we are unable to decide which movie titles to select.
            logger.error("Identical movie titles were found in {}".format(disc['path']))
            movie_titles = list()
            break
        elif titles[i]['size'] > (0.6 * movie_titles[-1]['size']):
            # Keep (arbitrarily) all versions of a movie (cinema, director's cut, etc.),
            # and discard additional features.
            movie_titles.append(titles[i])
    else:
        titles_found = len(movie_titles)
        if count:
            movie_titles = movie_titles[:count]
        logger.info("{0} movie titles selected among {1} found in \"{2}\"".format(len(movie_titles), titles_found, disc['path']))

    return movie_titles


def convert_movie_to_mkv(movie, disc, title, destination, profile):
    """Extract a movie title from a Blu-Ray disc and convert it into a MKV file.

    :param movie: name of the movie.
    :param disc: Blu-Ray disc containing the movie. A ``dictionary`` with ``type``, ``path`` and ``number`` of the disc.
    :param title: movie title to convert. A ``dictionary`` with the ``number`` and ``mkv`` file name that MakeMKV uses
                  internally to identifies the title.
    :param destination: directory path where the MKV file will be saved.
    :param profile: MakeMKV profile to use for the conversion.

    :return: a tuple with the conversion status (as a ``string``) and
             the path of the newly created MKV file (``Path`` object).
    """
    makemkv = [str(find_makemkv_binary()), '--profile={}'.format(profile), 'mkv', '{type}:{path}'.format(**disc),
               str(title['number']), str(destination)]

    conversion_status = None
    with subprocess.Popen(
            makemkv, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        line = last_line = p.stdout.readline()
        while line:
            line = line.rstrip()
            last_line = line
            logger.debug(line)

            match = re.search(MAKEMKV_OUTPUT_CONVERSION_SUCCESS, line)
            if match:
                conversion_status = match.group()

            line = p.stdout.readline()
        else:
            # Even when MakeMKV encounters an error, its status code is often set to 0.
            # That's why we use the last output line to check the conversion status.
            if conversion_status is None:
                conversion_status = last_line

    mkv = Path(destination) / title['mkv']
    if conversion_status != MAKEMKV_OUTPUT_CONVERSION_SUCCESS:
        try:
            mkv.unlink()
        except OSError:
            pass
        logger.error("Failed to convert title {0} of disc \"{1}\": {2}".format(title['number'], disc['path'], conversion_status))
        return conversion_status, None

    mkv_target = mkv.with_name('{0} - d{1}t{2}.mkv'.format(movie, disc['number'], title['number']))
    try:
        mkv.rename(mkv_target)
    except OSError:
        logger.warning("Unable to rename {}".format(mkv))
    else:
        mkv = mkv_target

    logger.info("Successfully converted title {0} of disc \"{1}\" into \"{2}\"".format(title['number'], disc['path'], mkv))

    return conversion_status, mkv


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    formatter = logging.Formatter(NZBGET_LOG_FORMAT)
    console.setFormatter(formatter)
    logger.addHandler(console)

    parser = argparse.ArgumentParser("Find Blu-Ray discs and convert movie titles to MKV with MakeMKV.")
    parser.add_argument('source', nargs='?', help="Directory where are stored Blu-Ray discs.")
    parser.add_argument('--movie', help="Name of the movie.")
    parser.add_argument('--profile', help="MakeMKV profile to use for the conversion.")
    parser.add_argument('--destination', help="Directory for storing MKV files.")
    parser.add_argument('--debug', action='store_true', help="Enable verbose mode.")

    args = parser.parse_args()

    if args.source:
        os.environ[ENVAR_DOWNLOAD_STATUS] = "SUCCESS"
        os.environ[ENVAR_DOWNLOAD_DIRECTORY] = args.source
        if args.movie:
            os.environ[ENVAR_DOWNLOAD_NAME] = args.movie
        if args.profile:
            os.environ[ENVAR_MAKEMKV_PROFILE] = args.profile
        if args.destination:
            os.environ[ENVAR_MKV_DESTINATION] = args.destination
        if not args.debug:
            logger.setLevel(logging.INFO)

    if (nzbget_is_configured() is False) or (not os.environ[ENVAR_DOWNLOAD_STATUS] == "SUCCESS"):
        sys.exit(POSTPROCESS_EXIT_CODE_ERROR)

    disc_type, discs = find_blu_ray_discs(os.environ[ENVAR_DOWNLOAD_DIRECTORY])
    for i in range(len(discs)):
        disc = {'type': disc_type, 'path': discs[i], 'number': i}
        titles = identify_movie_titles(disc, count=0)
        for title in titles:
            convert_movie_to_mkv(os.environ[ENVAR_DOWNLOAD_NAME], disc, title, os.environ[ENVAR_MKV_DESTINATION],
                                 os.environ[ENVAR_MAKEMKV_PROFILE])
