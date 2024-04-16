#!/usr/bin/env python
"""open forecast and observations and calibrates models using ensemble regression"""
import argparse  # para hacer el llamado desde consola
import time  # tomar el tiempo que lleva el codigo
import glob  # listar archivos
import calendar  # manejar meses del calendario
from pathlib import Path  # manejar path
import numpy as np
import model  # objeto y metodos asociados a los modelos
import observation # idem observaciones
import configuration
import pandas as pd

cfg = configuration.Config.Instance()

def main(args):
    
    coords = cfg.get('coords')
    conf_modelos = cfg.get('models')
    
    df_modelos = pd.DataFrame(conf_modelos[1:], columns=conf_modelos[0])
    
    if args.no_models:  # si hay que descartar algunos modelos
        df_modelos = df_modelos.query(f"model not in {args.no_models}")
    
    if args.models:  # si hay que incluir solo algunos modelos
        df_modelos = df_modelos.query(f"model in {args.models}")
        
    keys = ['nombre', 'instit', 'latn', 'lonn', 'miembros', 'plazos',\
            'fechai', 'fechaf', 'ext', 'rt_miembros']
    df_modelos.columns = keys
    
    modelos = df_modelos.to_dict('records')

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
    archivo = Path(PATH, cfg.get('folders').get('data').get('observations'),
                   'obs_' + args.variable[0] + '_' + str(year_verif) + '_' + SSS + '.npz')
    if archivo.is_file() and not args.OW:
        if args.CV:
            data = np.load(archivo)
            obs_dt = data['obs_dt']
            terciles = data['terciles']
            data.close()
    else:
        if args.CV:
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
            terciles = obs.computo_terciles(obs_dt, args.CV) # Obtain tercile limits
            categoria_obs = obs.computo_categoria(obs_dt, terciles)  #Define observed category
            np.savez(archivo, obs_dt=obs_dt, lats_obs=lats_obs, lons_obs=lons_obs,
                     terciles=terciles, cat_obs=categoria_obs, obs_3m=obs_3m)
            cfg.set_correct_group_to_file(archivo)  # Change group of file
    if np.logical_not(args.CV):
        archivo2 = Path(PATH, cfg.get('folders').get('data').get('observations'),
                        'obs_' + args.variable[0] + '_' + str(year_verif) + '_' + SSS + '_parameters.npz')
        if archivo2.is_file() and not args.OW:
            data = np.load(archivo2)
            obs_dt = data['obs_dt']
            terciles =data['terciles']
            data.close()
        else:
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
            terciles = obs.computo_terciles(obs_dt, args.CV) # Obtain tercile limits
            np.savez(archivo2, obs_dt=obs_dt, lats_obs=lats_obs, lons_obs=lons_obs,\
                     terciles=terciles) #Save observed variables
            cfg.set_correct_group_to_file(archivo2)  # Change group of file

    message = "Processing Models"
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

    RUTA = Path(PATH, cfg.get('folders').get('data').get('calibrated_forecasts'))
    for it in modelos:
        output = Path(RUTA, args.variable[0] + '_' + it['nombre'] + '_' + \
                          calendar.month_abbr[args.IC[0]] + '_' + SSS + \
                          '_gp_01_hind.npz')
        if args.CV:
            if output.is_file() and not args.OW:
                pass
            else:
                if np.logical_and(it['nombre'] == 'CFSv2', args.IC[0] == 11):
                    modelo = model.Model(it['nombre'], it['instit'], args.variable[0],\
                                     it['latn'], it['lonn'], it['miembros'] + 4, \
                                     it['plazos'], it['fechai'], it['fechaf'],\
                                     it['ext'], it['rt_miembros'] + 4)
                else:
                     modelo = model.Model(it['nombre'], it['instit'], args.variable[0],\
                                     it['latn'], it['lonn'], it['miembros'], \
                                     it['plazos'], it['fechai'], it['fechaf'],\
                                     it['ext'], it['rt_miembros'])

                [lats, lons, pronos] = modelo.select_months(args.IC[0], \
                                                            args.leadtime[0], \
                                                            coords['lat_s'], \
                                                            coords['lat_n'],
                                                            coords['lon_w'],
                                                            coords['lon_e'])
                pronos_dt = modelo.remove_trend(pronos, True)
                for_terciles = modelo.computo_terciles(pronos_dt, True)
                forecasted_category = modelo.computo_categoria(pronos_dt, for_terciles)
                [forecast_cr, Rmedio, Rmej, epsb, K] = modelo.ereg(pronos_dt,\
                                                                   obs_dt,
                                                                   True)
                pdf_intensity = modelo.pdf_eval(forecast_cr, epsb, obs_dt)
                prob_terc = modelo.probabilidad_terciles(forecast_cr, epsb,\
                                                         terciles)
                np.savez(output, lats=lats, lons=lons, pronos_dt=pronos_dt,
                         pronos_cr=forecast_cr, eps=epsb, Rm=Rmedio, Rb=Rmej, K=K,
                         peso=pdf_intensity, prob_terc=prob_terc,
                         forecasted_category=forecasted_category)
        else:

            output2 = Path(RUTA, args.variable[0] + '_' + it['nombre'] + '_' + \
                          calendar.month_abbr[args.IC[0]] + '_' + SSS + \
                          '_gp_01_hind_parameters.npz')
            if output2.is_file() and not args.OW:
                pass
            else:

#                if output.is_file() and not args.OW:
#                    data = np.load(output)
#                    pdf_intensity = data['peso']
#                    data.close()
#                else:
                if np.logical_and(it['nombre'] == 'CFSv2', args.IC[0] == 11):
                    modelo = model.Model(it['nombre'], it['instit'], args.variable[0],\
                                     it['latn'], it['lonn'], it['miembros'] + 4, \
                                     it['plazos'], it['fechai'], it['fechaf'],\
                                     it['ext'], it['rt_miembros'] + 4)
                else:
                    modelo = model.Model(it['nombre'], it['instit'], args.variable[0],\
                                     it['latn'], it['lonn'], it['miembros'], \
                                     it['plazos'], it['fechai'], it['fechaf'],\
                                     it['ext'], it['rt_miembros'])


                [lats, lons, pronos] = modelo.select_months(args.IC[0], \
                                                                args.leadtime[0], \
                                                                coords['lat_s'], \
                                                                coords['lat_n'],
                                                                coords['lon_w'],
                                                                coords['lon_e'])
                pronos_dt = modelo.remove_trend(pronos, True)
                for_terciles = modelo.computo_terciles(pronos_dt, True)
                forecasted_category = modelo.computo_categoria(pronos_dt, for_terciles)
                [forecast_cr, Rmedio, Rmej, epsb, K] = modelo.ereg(pronos_dt,\
                                                                       obs_dt,
                                                                       True)
                pdf_intensity = modelo.pdf_eval(forecast_cr, epsb, obs_dt)
                [pronos_dt, a1, b1] = modelo.remove_trend(pronos, args.CV)
                [a2, b2, Rmedio, Rmej, epsb, K] = modelo.ereg(pronos_dt,
                                                                  obs_dt,
                                                                  args.CV)

                np.savez(output2, lats=lats, lons=lons, pronos_dt=pronos_dt,
                             a1=a1, b1=b1, a2=a2, b2=b2, eps=epsb, Rm=Rmedio, Rb=Rmej, K=K,
                             peso=pdf_intensity)
                cfg.set_correct_group_to_file(output2)  # Change group of file


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
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--models', nargs='+', dest='models', default=[],
        choices=[item[0] for item in cfg.get('models')[1:]],
        help="Models to be included")
    group.add_argument('--no-models', nargs='+', dest='no_models', default=[],
        choices=[item[0] for item in cfg.get('models')[1:]],
        help="Models to be discarded")
    
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
        cfg.logger.error(f"Failed to run \"calibration.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"calibration.py\" ({err_pfx} errors): {end - start}" 
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

