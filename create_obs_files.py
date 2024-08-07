#!/usr/bin/env python

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

    base_path = cfg.get("folders").get("gen_data_folder")

    seas = range(args.IC[0] + args.leadtime[0], args.IC[0] + args.leadtime[0] + 3)
    sss = [i - 12 if i > 12 else i for i in seas]
    year_verif = 1991 if seas[-1] <= 12 else 1992
    sss_str = "".join(calendar.month_abbr[i][0] for i in sss)

    mensaje = "Processing " + args.variable[0] + " observations for " + sss_str + " initialized in " + str(args.IC[0])
    print(mensaje) if not cfg.get('use_logger') else cfg.logger.info(mensaje)

    # Creando archivo 1 -- calibration.py
    if args.CV:
        archivo1 = Path(base_path, cfg.get('folders').get('data').get('observations'),
                        'obs_' + args.variable[0] + '_' + str(year_verif) + '_' + sss_str + '.npz')
        if not archivo1.is_file() or args.OW:
            if args.variable[0] == 'prec':
                obs = observation.Observ('cpc', args.variable[0], 'Y', 'X', 1991, 2020)
            else:
                obs = observation.Observ('ghcn_cams', args.variable[0], 'Y', 'X', 1991, 2020)

            [lats_obs, lons_obs, obs_3m] = obs.select_months(calendar.month_abbr[sss[-1]],
                                                             year_verif,
                                                             coords['lat_s'],
                                                             coords['lat_n'],
                                                             coords['lon_w'],
                                                             coords['lon_e'])
            obs_dt = obs.remove_trend(obs_3m, args.CV)  # Standardize and detrend observation
            terciles = obs.computo_terciles(obs_dt, args.CV)  # Obtain tercile limits
            categoria_obs = obs.computo_categoria(obs_dt, terciles)  # Define observed category
            np.savez(archivo1, obs_dt=obs_dt, lats_obs=lats_obs, lons_obs=lons_obs,
                     terciles=terciles, cat_obs=categoria_obs, obs_3m=obs_3m)
            cfg.set_correct_group_to_file(archivo1)  # Change group of file

    # Creando archivo 2 (se utiliza solo con la validación cruzada (cross-validation) -- calibration.py
    if np.logical_not(args.CV):
        archivo2 = Path(base_path, cfg.get('folders').get('data').get('observations'),
                        'obs_' + args.variable[0] + '_' + str(year_verif) + '_' + sss_str + '_parameters.npz')
        if not archivo2.is_file() or args.OW:
            if args.variable[0] == 'prec':
                obs = observation.Observ('cpc', args.variable[0], 'Y', 'X', 1991, 2020)
            else:
                obs = observation.Observ('ghcn_cams', args.variable[0], 'Y', 'X', 1991, 2020)

            [lats_obs, lons_obs, obs_3m] = obs.select_months(calendar.month_abbr[sss[-1]],
                                                             year_verif,
                                                             coords['lat_s'],
                                                             coords['lat_n'],
                                                             coords['lon_w'],
                                                             coords['lon_e'])
            obs_dt = obs.remove_trend(obs_3m, args.CV)  # Standardize and detrend observation
            terciles = obs.computo_terciles(obs_dt, args.CV)  # Obtain tercile limits
            np.savez(archivo2, obs_dt=obs_dt, lats_obs=lats_obs, lons_obs=lons_obs,
                     terciles=terciles)  # Save observed variables
            cfg.set_correct_group_to_file(archivo2)  # Change group of file

    # Creando archivo con quintiles (archivo con extremos para gráficos SISSA) -- calibration_sissa.py
    archivo3 = Path(base_path, cfg.get('folders').get('data').get('observations'),
                    'obs_extremes_' + args.variable[0] + '_' + str(year_verif) +
                    '_' + sss_str + '_parameters.npz')
    if not archivo3.is_file() or args.OW:
        if args.variable[0] == 'prec':
            obs = observation.Observ('cpc', args.variable[0], 'Y', 'X', 1991, 2020)
        else:
            obs = observation.Observ('ghcn_cams', args.variable[0], 'Y', 'X', 1991, 2020)
        [lats_obs, lons_obs, obs_3m] = obs.select_months(calendar.month_abbr[sss[-1]],
                                                         year_verif,
                                                         coords['lat_s'],
                                                         coords['lat_n'],
                                                         coords['lon_w'],
                                                         coords['lon_e'])
        obs_dt = obs.remove_trend(obs_3m, args.CV)  # Standardize and detrend observation
        quintiles = obs.computo_quintiles(obs_dt, args.CV)  # Obtain tercile limits
        np.savez(archivo3, obs_dt=obs_dt, lats_obs=lats_obs, lons_obs=lons_obs,
                 quintiles=quintiles)  # Save observed variables
        cfg.set_correct_group_to_file(archivo3)  # Change group of file


# ==================================================================================================


if __name__ == "__main__":
    # OBS: este script crea varias veces el mismo archivo, la que un mismo trimestre se repite con
    #      múltiples leadtimes, sin embargo, este re-trabajo permite comprobar que el script de
    #      generación del descriptor para los archivos observados "create_obs_files_descriptors.py"
    #      funciona correctamente (puesto que ambos scripts, siguiendo enfoques diferentes, producen
    #      los mismos archivos). La manera de crear los archivos observados que se utiliza en este script
    #      fue derivada de la calibración (puesto que normalmente, estos archivos con datos observados
    #      son creados automáticamente cuando se realiza la calibración).

    # Defines parser data
    parser = argparse.ArgumentParser(description='Externally creates observations files (normally these files '
                                                 'are created internally when running the calibration).')
    parser.add_argument('--variables', nargs='+',
                        default=["tref", "prec"], choices=["tref", "prec"],
                        help='Variables that will be considered.')
    parser.add_argument('--CV', action='store_true', help='Cross-validated mode')
    parser.add_argument('--OW', action='store_true', help='Overwrite previous observations files')

    # Extract data from args
    main_args = parser.parse_args()

    # Set error as not detected
    error_detected = False

    # Run obs files creation
    start = time.time()
    try:
        cfg.logger.info("Starting obs files creation")
        for v in main_args.variables:  # loop sobre las variables a calibrar
            for m in range(1, 12+1):  # loop over IC --> Month of initial conditions (from 1 for Jan to 12 for Dec)
                for lt in range(1, 7+1):  # loop over leadtime --> Forecast leadtime (in months, from 1 to 7)
                    main(argparse.Namespace(variable=[v], IC=[m], leadtime=[lt], CV=main_args.CV, OW=main_args.OW))
    except Exception as e:
        error_detected = True
        cfg.logger.error(f"Failed to run \"create_obs_files.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"create_obs_files.py\" ({err_pfx} errors): {end - start}"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
