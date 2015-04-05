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
MAKEMKV_PATTERN_TITLE_INFO = 'TINFO:(?P<number>\d+),\d+,\d+,'
MAKEMKV_PATTERN_TITLE_FILE = '{}"(?P<fname>.+\.mkv)"'.format(MAKEMKV_PATTERN_TITLE_INFO)
MAKEMKV_PATTERN_TITLE_DETAILS = '{}"(?P<name>.+) - (?P<chapters>\d+) chapter\(s\) , ' \
                                '(?P<size>\d+\.?\d*) GB"'.format(MAKEMKV_PATTERN_TITLE_INFO)
MSG_END_CONVERSION = "Successfully converted {} to MKV."
NZBGET_LOG_FORMAT = "[%(levelname)s] %(message)s"
POSTPROCESS_EXIT_CODE_ERROR = 94
POSTPROCESS_EXIT_CODE_SUCCESS = 93  # Returned code when post-process is successful

REQUIRED_OPTIONS = (ENVAR_MAKEMKV_PROFILE, ENVAR_MKV_DIRECTORY)


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def is_configured():
    missing_opt = False
    for option in REQUIRED_OPTIONS:
        if option not in os.environ:
            logger.error("The following configuration option must be defined: {}.".format(option))
            missing_opt = True
    if missing_opt:
        return False
    return True


def find_makemkv_binary():
    try:
        bin_path = subprocess.check_output(
            ['which', MAKEMKV_BINARY], stderr=subprocess.DEVNULL, universal_newlines=True)
    except subprocess.CalledProcessError:
        logger.error("MakeMKV binary not found.")
        return None
    return pathlib.PurePath(bin_path.rstrip())


def find_blu_ray_sources(path, multi=1):
    sources_type = None
    sources = list(path.rglob('BDMV/index.bdmv')) or None

    if sources:
        sources_type = "file"
        for i in range(len(sources)):
            sources[i] = sources[i].parents[1]
    else:
        iso_images = path.rglob('*.iso')
        sources = sorted(iso_images, key=lambda iso: iso.stat().st_size, reverse=True) or None
        if sources:
            sources_type = "iso"

    if sources:
        sources_number = len(sources)
        if multi == 1:
            if sources_number > 1:
                logger.warning("More than one blu-ray source was found.")
            sources = sources[0]
        elif multi > 1:
            if sources_number != multi:
                logger.warning("{0} blu-ray sources were found ({1} asked).".format(sources_number, multi))
            sources = sources[:multi]

    return sources_type, sources


def identify_movie_titles(source, multi=1):
    makemkv = find_makemkv_binary()
    title_fname = re.compile(MAKEMKV_PATTERN_TITLE_FILE)
    title_details = re.compile(MAKEMKV_PATTERN_TITLE_DETAILS)
    titles = list()

    with subprocess.Popen(
            [makemkv, '-r', 'info', '{type}:{path}'.format(**source)],
            stderr=subprocess.STDOUT,  stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        line = p.stdout.readline()
        while line:
            line = line.rstrip()
            m = title_fname.match(line)
            if m is not None:
                fname = m.group('fname')
                line = p.stdout.readline()
                while line:
                    line = line.rstrip()
                    m = title_details.match(line)
                    if m is not None:
                        number = int(m.group('number'))
                        chapters = int(m.group('chapters'))
                        size = float(m.group('size'))
                        titles.append({'number': number, 'fname': fname, 'chapters': chapters, 'size': size})
                        break
                    line = p.stdout.readline()
            line = p.stdout.readline()

    if not titles:
        return None

    titles = sorted(titles, key=lambda title: title['chapters'], reverse=True)
    if multi == 1:
        if len(titles) > 1:
            if titles[0]['chapters'] == titles[1]['chapters']:
                logger.warning("Two movie titles with the same number of chapters were found.")
                return None
        return titles[0]
    elif multi > 1:
        titles_number = len(titles)
        if multi > titles_number:
            logger.warning("Only {0} titles are available ({1} asked).".format(titles_number, multi))
        return titles[:multi]

    return titles


def convert_to_mkv(movie, source, title, destination, profile):
    makemkv = find_makemkv_binary()

    p = subprocess.Popen(
        [makemkv, '--profile={}'.format(profile), 'mkv', '{type}:{path}'.format(**source), title['number'], destination],
        stderr=subprocess.STDOUT, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True)
    line = p.stdout.readline()
    while line:
        line = line.rstrip()
        logger.debug(line)
        line = p.stdout.readline()
    p.wait()

    mkv_path = destination / title['fname']
    if p.returncode != 0:
        logger.error("An error was encountered during the conversion. Please check logs.")
        try:
            mkv_path.unlink()
        except OSError:
            pass
        return None

    mkv_new_path = mkv_path.with_name('{}.mkv'.format(movie))
    try:
        mkv_path.rename(mkv_new_path)
    except OSError:
        if not mkv_path.is_file():
            logger.error("An error was encountered during the conversion. Please check logs.")
        else:
            logger.warning("Unable to rename {} to {}".format(mkv_path, mkv_new_path))
        return None

    return mkv_new_path


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    console.setFormatter(NZBGET_LOG_FORMAT)
    logger.addHandler(console)

    if is_configured() is False:
        sys.exit(POSTPROCESS_EXIT_CODE_ERROR)
