
from pathlib import Path
from typing import TextIO

import argparse
import time
import logging
import os
import re


def dir_path(string):
    if os.path.isdir(string):
        return string
    else:
        raise NotADirectoryError(string)


def write_file_desc(fp_file: TextIO, fcst_file_type: str, fcst_file_path: Path):
    fp_file.write('  - {\n')
    fp_file.write(f'    type: "{fcst_file_type}",\n')
    fp_file.write(f'    path: ".",\n')
    fp_file.write(f'    name: "{fcst_file_path.name}",\n')
    fp_file.write('  }\n')


def main(main_args: argparse.Namespace):
    logging.info(f"Current dir: {main_args.folder}")

    with open(main_args.output, 'w') as fp_desc:
        fp_desc.write("files:\n")
        for archivo in [f for f in os.listdir(main_args.folder) if re.match(main_args.pattern, f)]:
            logging.info(f"Adding descriptor for: {archivo}; to file: {fp_desc.name}")
            write_file_desc(fp_desc, main_args.type, Path(main_args.output, archivo))


# ==================================================================================================
if __name__ == "__main__":

    # Conf logger
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    # Define parser data
    parser = argparse.ArgumentParser(description='Create descriptors for files in a folder')
    parser.add_argument('-f', '--folder', type=dir_path, default=Path().resolve(), help='Folder who files are located.')
    parser.add_argument('-p', '--pattern', help='Pattern that allow to select files to be processed.')
    parser.add_argument('-t', '--type', help='Type of files to be added to the descriptor file.')
    parser.add_argument('-o', '--output', help='The output file to which the descriptors will be added.')

    # Extract data from args
    args = parser.parse_args()

    print(args)

    # Set errors detected flag to False
    error_detected = False

    # Run plotting
    start = time.time()
    try:
        main(args)
    except Exception as e:
        error_detected = True
        logging.error(f"Failed to run \"create_descriptors_manually.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"create_output_files_descriptors.py\" ({err_pfx} errors): {end - start}"
        logging.info(message)
