#!/usr/bin/env python

"""
See https://edx-wiki.atlassian.net/wiki/display/ENG/PO+File+workflow

This task merges and compiles the human-readable .po files on the
local filesystem into machine-readable .mo files. This is typically
necessary as part of the build process since these .mo files are
needed by Django when serving the web app.

The configuration file (in edx-platform/conf/locale/config.yaml) specifies which
languages to generate.

"""

import logging
import os
import sys

from polib import pofile

from i18n import config, Runner
from i18n.execute import execute

LOG = logging.getLogger(__name__)
DEVNULL = open(os.devnull, "wb")


def merge(locale, target='django.po', sources=('django-partial.po',), fail_if_missing=True):
    """
    For the given locale, merge the `sources` files to become the `target`
    file.  Note that the target file might also be one of the sources.

    If fail_if_missing is true, and the files to be merged are missing,
    throw an Exception, otherwise return silently.

    If fail_if_missing is false, and the files to be merged are missing,
    just return silently.

    """
    LOG.info('Merging {target} for locale {locale}'.format(target=target, locale=locale))
    locale_directory = config.CONFIGURATION.get_messages_dir(locale)
    try:
        validate_files(locale_directory, sources)
    except Exception:  # pylint: disable=broad-except
        if not fail_if_missing:
            return
        raise

    # merged file is merged.po
    merge_cmd = 'msgcat -o merged.po ' + ' '.join(sources)
    execute(merge_cmd, working_directory=locale_directory)

    # clean up redunancies in the metadata
    merged_filename = locale_directory.joinpath('merged.po')
    clean_pofile(merged_filename)

    # rename merged.po -> django.po (default)
    target_filename = locale_directory.joinpath(target)
    os.rename(merged_filename, target_filename)


def merge_files(locale, fail_if_missing=True):
    """
    Merge all the files in `locale`, as specified in config.yaml.
    """
    for target, sources in config.CONFIGURATION.generate_merge.items():
        merge(locale, target, sources, fail_if_missing)


def clean_pofile(path):
    """
    Clean various aspect of a .po file.

    Fixes:

        - Removes the ,fuzzy flag on metadata.

        - Removes occurrence line numbers so that the generated files don't
          generate a lot of line noise when they're committed.

        - Removes any flags ending with "-format".  Mac gettext seems to add
          these flags, Linux does not, and we don't seem to need them.  By
          removing them, we reduce the unimportant differences that clutter
          diffs as different developers work on the files.

    """
    # Reading in the .po file and saving it again fixes redundancies.
    pomsgs = pofile(path)
    # The msgcat tool marks the metadata as fuzzy, but it's ok as it is.
    pomsgs.metadata_is_fuzzy = False
    for entry in pomsgs:
        # Remove line numbers
        entry.occurrences = [(filename, None) for filename, __ in entry.occurrences]
        # Remove -format flags
        entry.flags = [f for f in entry.flags if not f.endswith("-format")]
    pomsgs.save()


def validate_files(directory, files_to_merge):
    """
    Asserts that the given files exist.
    files_to_merge is a list of file names (no directories).
    directory is the directory (a path object from path.py) in which the files should appear.
    raises an Exception if any of the files are not in dir.
    """
    for path in files_to_merge:
        pathname = directory.joinpath(path)
        if not pathname.exists():
            raise Exception("I18N: Cannot generate because file not found: {0}".format(pathname))


class Generate(Runner):
    def add_args(self):
        self.parser.description = "Generate merged and compiled message files."
        self.parser.add_argument("--strict", action='store_true', help="Complain about missing files.")
        self.parser.add_argument("--ltr", action='store_true', help="Only generate for LTR languages.")
        self.parser.add_argument("--rtl", action='store_true', help="Only generate for RTL languages.")

    def run(self, args):
        """
        Main entry point for script
        """
        logging.basicConfig(stream=sys.stdout, level=logging.INFO)

        if args.ltr:
            langs = config.CONFIGURATION.ltr_langs
        elif args.rtl:
            langs = config.CONFIGURATION.rtl_langs
        else:
            langs = config.CONFIGURATION.translated_locales

        for locale in langs:
            merge_files(locale, fail_if_missing=args.strict)
        # Dummy text is not required. Don't raise exception if files are missing.
        for locale in config.CONFIGURATION.dummy_locales:
            merge_files(locale, fail_if_missing=False)

        compile_cmd = 'django-admin.py compilemessages -v{}'.format(args.verbose)
        if args.verbose:
            stderr = None
        else:
            stderr = DEVNULL
        execute(compile_cmd, working_directory=config.BASE_DIR, stderr=stderr)

main = Generate()  # pylint: disable=invalid-name

if __name__ == '__main__':
    main()
