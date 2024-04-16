"""
calculated mme regression parameters against observations
"""
#!/usr/bin/env python
import argparse  # parse command line options
import time  # test time consummed
import datetime
import warnings
import glob
from pathlib import Path
import calendar
import numpy as np
import model
import ereg  # apply ensemble regression to multi-model ensemble
import configuration
import pandas as pd

cfg = configuration.Config.Instance()

warnings.filterwarnings("ignore", category=RuntimeWarning)

def main(args):
    
    coords = cfg.get('coords')
    conf_modelos = cfg.get('models')
    
    df_modelos = pd.DataFrame(conf_modelos[1:], columns=conf_modelos[0])
    
    if args.no_models:  # si hay que descartar algunos modelos
        df_modelos = df_modelos.query(f"model not in {args.no_models}")
        
    keys = ['nombre', 'instit', 'latn', 'lonn', 'miembros', 'plazos',\
            'fechai', 'fechaf', 'ext', 'rt_miembros']
    df_modelos.columns = keys
    
    modelos = df_modelos.to_dict('records')

    PATH = cfg.get("folders").get("gen_data_folder")
    
    nmodels = len(modelos)
    ny = int(np.abs(coords['lat_n'] - coords['lat_s']) + 1)
    nx = int(np.abs (coords['lon_e'] - coords['lon_w']) + 1) #does for domains beyond greenwich
    nyears = 30 # int(modelos[0]['fechaf'] - modelos[0]['fechai'] + 1)
    for_dt = np.array([]).reshape(nyears, ny, nx, 0) #[years lats lons members]
    if args.wtech[0] == 'pdf_int':
        weight = np.array([]).reshape(nyears, ny, nx, 0)
    elif args.wtech[0] == 'mean_cor':
        rmean = np.array([]).reshape(ny, nx, 0)
    nmembers = np.empty([nmodels], dtype=int)
    #defino ref dataset y target season
    seas = range(args.IC[0] + args.leadtime[0], args.IC[0] + args.leadtime[0] + 3)
    sss = [i - 12 if i > 12 else i for i in seas]
    year_verif = 1991 if seas[-1] <= 12 else 1992
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)
    message = 'Var:' + args.variable[0] + ' IC:' + calendar.month_abbr[args.IC[0]] +\
              ' Target season:' + SSS + ' ' + args.wtech[0]
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
    #obtengo datos observados
    archivo = Path(PATH, cfg.get('folders').get('data').get('observations'),
                   'obs_' + args.variable[0] + '_' + str(year_verif) + '_' + SSS + '_parameters.npz')
    data = np.load(archivo)
    terciles = data['terciles']
    obs_dt = data['obs_dt']
    lats = data['lats_obs']
    lons = data['lons_obs']
    j = 0
    for it in modelos:
        modelo = model.Model(it['nombre'], it['instit'], args.variable[0],\
                            it['latn'], it['lonn'], it['miembros'], \
                            it['plazos'], it['fechai'], it['fechaf'],\
                            it['ext'], it['rt_miembros'])
        #abro archivo modelo
        archivo = Path(PATH, cfg.get('folders').get('data').get('calibrated_forecasts'),
                       args.variable[0] + '_' + it['nombre'] + '_' +\
                       calendar.month_abbr[args.IC[0]] + '_' + SSS +\
                       '_gp_01_hind_parameters.npz')
        data = np.load(archivo)
        f_dt = data['pronos_dt']
        nmembers[j] = np.shape(f_dt)[1]
        #junto pronos hindcast
        for_dt = np.concatenate((for_dt, np.rollaxis(f_dt, 1, 4)), axis=3)
        #extraigo info del peso segun la opcion por la que elijo pesar
        if args.wtech[0] == 'pdf_int':
            peso = data['peso']
            weight = np.concatenate((weight, peso[:, :, :][:, :, :,
                                                              np.newaxis]),
                                    axis=3)
            peso = []
        elif args.wtech[0] == 'mean_cor':
            Rm = data['Rm']
            rmean = np.concatenate((rmean, Rm[:, :, np.newaxis]), axis=2)
            Rm = []
        j += 1
    lat = lats
    lon = lons
    nlats = np.shape(lat)[0]
    nlons = np.shape(lon)[0]

    # calculo matriz de peso
    if args.wtech[0] == 'pdf_int':
        #calculo para cada año la probabilidad de cad atercil para cada
        #miembro de ensamble de cada modelo. Despues saco el promedio
        #peso: nro veces max de la intensidad de la pdf / anios
        maximo = np.ndarray.argmax(weight, axis=3) #posicion en donde se da el maximo
        ntimes = np.shape(weight)[0]
        weight = []
        peso = np.empty([nlats, nlons, nmodels])
        for i in np.arange(nmodels):
            peso[:, :, i] = np.nanmean(maximo == i, axis=0)
        weight = np.tile(peso, (2, 1, 1, 1)) #2 nlat nlon nmodels

    elif args.wtech[0] == 'mean_cor':
        rmean[np.where(np.logical_or(rmean < 0, ~np.isfinite(rmean)))] = 0
        rmean[np.nansum(rmean[:, :, :], axis=2) == 0, :] = 1
        peso = rmean / np.tile(np.nansum(rmean, axis=2)[:, :, np.newaxis], [1, 1, nmodels])
        weight = np.tile(peso, (2, 1, 1, 1))  #2 nlat nlon nmodels

    elif args.wtech[0] == 'same': #mismo peso para todos
        weight = np.ones([2, nlats, nlons, nmodels]) / nmodels

    ntimes = np.shape(for_dt)[0]
    weight = np.tile(weight[0, :, :, :], (ntimes, 1, 1, 1)) / nmembers
    archivo = Path(PATH, cfg.get('folders').get('data').get('combined_forecasts'),
                   args.variable[0]+'_mme_' + calendar.month_abbr[args.IC[0]] +\
                   '_' + SSS + '_gp_01_' + args.wtech[0] + '_wsereg' +\
                   '_hind_parameters.npz')
    if not(archivo.is_file()) or args.OW:
        #ereg con el smme pesado
        for_dt = np.rollaxis(for_dt * np.repeat(weight, nmembers, axis=3), 3, 1)
        [a_mme, b_mme, R_mme, Rb_mme, eps_mme, Kmax_mme,
         K_mme] = ereg.ensemble_regression(for_dt, obs_dt, False)
        np.savez(archivo, a_mme=a_mme, b_mme=b_mme, R_mme=R_mme,
                 Rb_mme=Rb_mme, eps_mme=eps_mme, Kmax_mme=Kmax_mme,
                 K_mme=K_mme)

# ==================================================================================================
if __name__ == "__main__":
    
    # Defines parser data
    parser = argparse.ArgumentParser(description='Combining models')
    parser.add_argument('variable', type=str, nargs=1, 
        help='Variable to calibrate (prec or tref)')
    parser.add_argument('--IC', dest='IC', type=int, nargs=1,
        help='Initial conditions (month) in number')
    parser.add_argument('--leadtime', dest='leadtime', type=int, nargs=1,
        help='Forecast leadtime (in months, from 1 to 7)')
    parser.add_argument('--OW', 
        help='Overwrite previous calibrations', action='store_true')
    parser.add_argument('--no-models', nargs='+', dest='no_models', default=[],
        choices=[item[0] for item in cfg.get('models')[1:]], 
        help='Models to be discarded')
    parser.add_argument("--weight_tech", required=True, nargs=1, 
        choices=['pdf_int', 'mean_cor', 'same'], dest='wtech', 
        help='Relative weight between models')
    
    # Extract data from args
    args = parser.parse_args()

    # Set error as not detected
    error_detected = False
  
    # Run mme parameters extraction
    start = time.time()
    try:
        main(args)
    except Exception as e:
        error_detected = True
        cfg.logger.error(f"Failed to run \"get_mme_parameters.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"get_mme_parameters.py\" ({err_pfx} errors): {end - start}" 
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)


