
import configuration

import argparse
import time
import calendar

from pathlib import Path
from typing import TextIO

cfg = configuration.Config.Instance()


def write_file_desc(fp_file: TextIO, fcst_file_type: str, fcst_file_path: Path):
    fp_file.write('  - {\n')
    fp_file.write(f'    type: "{fcst_file_type}",\n')
    fp_file.write(f'    path: ".",\n')
    fp_file.write(f'    name: "{fcst_file_path.name}",\n')
    fp_file.write('  }\n')


def def_new_file_name(variable, ic_month, year):
    leadtime = 1
    seas = range(ic_month + leadtime, ic_month + leadtime + 3)
    season = "".join(calendar.month_abbr[i][0] for i in [i - 12 if i > 12 else i for i in seas])
    # Definir y retornar la primera parte del nombre del archivo
    return f'obs_{variable}_{year}_{season}.npz'


def main(main_args: argparse.Namespace):
    desc_file_name = 'observed_data_descriptors.yaml'
    forecasts_folder = Path(cfg.get('folders').get('gen_data_folder'),
                            cfg.get('folders').get('data').get('observations'))

    with open(Path(forecasts_folder, desc_file_name), 'w') as fp_desc:
        fp_desc.write('files:\n')

        for v in main_args.variables:
            for ic in main_args.ic_months:
                for y in [main_args.first_hindcast_year, main_args.first_hindcast_year+1]:
                    # Los trimestres NDJ, DJF y JFM no son válidos para el primer año
                    if y == main_args.first_hindcast_year and ic > 9:
                        continue
                    # Los trimestres ASO, SON, OND no son válidos para el segundo año
                    if y == main_args.first_hindcast_year+1 and 6 < ic < 10:
                        continue
                    # Agregar archivo al descriptor, cuando corresponda
                    # OBS: solo se describe el archivo con la variable obs_3m
                    archivo = Path(forecasts_folder, def_new_file_name(v, ic, y))
                    write_file_desc(fp_desc, 'ereg_obs_data', archivo)


# ==================================================================================================
if __name__ == "__main__":

    # Define parser data
    parser = argparse.ArgumentParser(description='Create descriptors for forecasts')
    parser.add_argument('--variables', nargs='+',
                        default=["tref", "prec"], choices=["tref", "prec"],
                        help='Variables that was considered in the forecast generation process.')
    parser.add_argument('--ic-months', type=int, nargs='+', dest='ic_months',
                        default=range(1, 12+1), choices=range(1, 12+1),
                        help='Months of initial conditions (from 1 for Jan to 12 for Dec)')
    parser.add_argument('--first_hindcast_year', type=int, default=1982,
                        help='First hindcast period year (ej: 1982)')

    # Extract data from args
    args = parser.parse_args()

    # Set error as not detected
    error_detected = False

    # Run plotting
    start = time.time()
    try:
        main(args)
    except Exception as e:
        error_detected = True
        cfg.logger.error(f"Failed to run \"create_output_files_descriptors.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"create_output_files_descriptors.py\" ({err_pfx} errors): {end - start}"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
