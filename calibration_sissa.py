#!/usr/bin/env python
"""open forecast and observations and calibrates models using ensemble regression"""
import argparse  # para hacer el llamado desde consola
import time  # tomar el tiempo que lleva el código
import calendar  # manejar meses del calendario
from pathlib import Path  # manejar path
import numpy as np
import observation  # idem observaciones
import configuration

cfg = configuration.Config.Instance()


def main(args):
    coords = cfg.get('coords')

    PATH = cfg.get("folders").get("gen_data_folder")
    """ref dataset: depende de CI del prono y plazo.
    Ej: si IC prono es Jan y plazo 1 entonces FMA en primer tiempo 1982. Si IC
    prono es Dec y plazo 2 entonces FMA en primer tiempo es 1983."""
    seas = range(args.IC[0] + args.leadtime[0], args.IC[0] + args.leadtime[0] + 3)
    sss = [i - 12 if i > 12 else i for i in seas]
    year_verif = 1991 if seas[-1] <= 12 else 1992
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)
    message = "Calibrating " + args.variable[0] + " forecasts for " + SSS + \
              " initialized in " + str(args.IC[0])
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

    message = "Processing Observations"
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
    archivo2 = Path(PATH, cfg.get('folders').get('data').get('observations'),
                    'obs_extremes_' + args.variable[0] + '_' + str(year_verif) +
                    '_' + SSS + '_parameters.npz')

    # Si archivo2 ya existe, no se lo vuelve a crear a menos esto se solicite
    # explícitamente con el parámetro --OW (Overwrite previous calibrations)
    if archivo2.is_file() and not args.OW:
        return

    if args.variable[0] == 'prec':
        obs = observation.Observ('cpc', args.variable[0], 'Y', 'X', 1991,
                                 2020)
    else:
        obs = observation.Observ('ghcn_cams', args.variable[0], 'Y', 'X', 1991,
                                 2020)
    [lats_obs, lons_obs, obs_3m] = obs.select_months(calendar.month_abbr[\
                                                                         sss[-1]],
                                                              year_verif,
                                                              coords['lat_s'],
                                                              coords['lat_n'],
                                                              coords['lon_w'],
                                                              coords['lon_e'])
    obs_dt = obs.remove_trend(obs_3m, args.CV) #Standardize and detrend observation
    quintiles = obs.computo_quintiles(obs_dt, args.CV) # Obtain tercile limits
    np.savez(archivo2, obs_dt=obs_dt, lats_obs=lats_obs, lons_obs=lons_obs,\
             quintiles=quintiles) #Save observed variables


# ==================================================================================================
if __name__ == "__main__":

    # Defines parser data
    parser = argparse.ArgumentParser(description='Calibrates model using Ensemble Regression.')
    parser.add_argument('variable', type=str, nargs=1,
                        help='Variable to calibrate (prec or tref)')
    parser.add_argument('IC', type=int, nargs=1,
                        help='Month of initial conditions (from 1 for Jan to 12 for Dec)')
    parser.add_argument('leadtime', type=int, nargs=1,
                        help='Forecast leadtime (in months, from 1 to 7)')
    parser.add_argument('--CV', action='store_true',
                        help='Cross-validated mode')
    parser.add_argument('--OW', action='store_true',
        help='Overwrite previous calibrations')

    # Extract data from args
    args = parser.parse_args()

    # Set error as not detected
    error_detected = False

    # Run calibration
    start = time.time()
    try:
        main(args)
    except Exception as e:
        error_detected = True
        cfg.logger.error(f"Failed to run \"calibration_sissa.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"calibration_sissa.py\" ({err_pfx} errors): {end - start}"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

