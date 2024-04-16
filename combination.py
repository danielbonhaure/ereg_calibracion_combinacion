"""
combines forecast to obtain probabilistic forecast for terciles combining
forecasts using wpdf and wsereg techniques to calibrated models
"""
#!/usr/bin/env python
import argparse  # parse command line options
import time  # test time consummed
import warnings
import glob
from pathlib import Path
import calendar
import numpy as np
import ereg  # apply ensemble regression to multi-model ensemble
import configuration
import pandas as pd
import os

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
    if args.ctech == 'wpdf':
        prob_terciles = np.array([]).reshape(2, nyears, ny, nx, 0) #[cat years lats lons models]
    elif args.ctech == 'wsereg':
        for_dt = np.array([]).reshape(nyears, ny, nx, 0) #[years lats lons members]
    else:
        for_category = np.array([]).reshape(3, nyears, ny, nx, 0) #[car years lats lons members]

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
    message = "Combining forecasts: " + SSS + " " + args.variable[0] + " Initialized in " +\
               calendar.month_abbr[args.IC[0]] + " using " + args.ctech + " " + args.wtech[0]
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
    
    i = 0
    for it in modelos:
        #abro archivo modelo
        archivo = Path(PATH, cfg.get('folders').get('data').get('calibrated_forecasts'),
                       args.variable[0] + '_' + it['nombre'] + '_' +\
                       calendar.month_abbr[args.IC[0]] + '_' + SSS +\
                       '_gp_01_hind.npz')
        message = f"Se va a intentar abrir el archivo: {archivo}. Además archivo.is_file() = {archivo.is_file()}." 
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        if archivo.is_file():
            data = np.load(archivo)
            """
            extraigo datos de cada modelo. esto depende del tipo de consolidado
            con wpdf solo necesito la probabilidad y el peso de cada mod
            con wsereg necesito el prono estandarizado y el peso
            con count necesito la categoria asignada
            """
            if args.ctech == 'wpdf':
                prob_terc = data['prob_terc']
                nmembers[i] = prob_terc.shape[2]
                prob_terc = np.nanmean(prob_terc, axis=2)
                prob_terciles = np.concatenate((prob_terciles,
                                                prob_terc[:, :, :, :,
                                                          np.newaxis]), axis=4)
                prob_terc = []
                #prob_terciles [cat year lats lons models]
            elif args.ctech == 'wsereg':
                f_dt = data['pronos_dt']
                nmembers[i] = f_dt.shape[1]
                for_dt = np.concatenate((for_dt, np.rollaxis(f_dt, 1, 4)), axis=3)
                f_dt = []
                #for_dt[years lats lons nmembers]
            else:
                f_cat = data['forecasted_category']
                nmembers[i] = f_cat.shape[2]
                for_category = np.concatenate((for_category,
                                               np.rollaxis(f_cat, 2, 5)),
                                              axis=4)
                f_cat = []
                #for_category[cat years lats lons members]
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
            i += 1

    lat = data['lats']
    lon = data['lons']
    #obtengo datos observados
    archivo = Path(PATH, cfg.get('folders').get('data').get('observations'),
                   'obs_'+args.variable[0] + '_' + str(year_verif) + '_' + SSS + '.npz')
    data = np.load(archivo)
    obs_terciles = data['cat_obs']
    if args.ctech == 'wsereg':
        terciles = data['terciles']
        obs_dt = data['obs_dt']

    [ntimes, nlats, nlons] = obs_terciles.shape[1:]
    #calculo matriz de peso
    if args.wtech[0] == 'pdf_int':
        #calculo para cada año la probabilidad de cad atercil para cada
        #miembro de ensamble de cada modelo. Despues saco el promedio
        #peso: nro veces max de la intensidad de la pdf / anios
        maximo = np.ndarray.argmax(weight, axis=3) #posicion en donde se da el maximo
        weight = []
        peso = np.empty([nyears, nlats, nlons, nmodels])
        CV = np.logical_not(np.identity(ntimes))
        for i in np.arange(nmodels):
            for j in np.arange(nyears):
                peso[j, :, :, i] = np.sum(maximo[CV[:, j], :, :] == i,\
                                          axis=0) / (ntimes - 1)

        weight = np.tile(peso, (2, 1, 1, 1, 1)) #2 ntimes nlat nlon nmodels

    elif args.wtech[0] == 'mean_cor':
        rmean[np.where(np.logical_and(rmean < 0, ~np.isnan(rmean)))] = 0
        rmean[np.sum(rmean[:, :, :], axis=2) == 0, :] = 1
        peso = rmean / np.tile(np.sum(rmean, axis=2)[:, :, np.newaxis], [1, 1, nmodels])
        weight = np.tile(peso, (2, ntimes, 1, 1, 1))  #2 ntimes nlat nlon nmodels

    elif args.wtech[0] == 'same': #mismo peso para todos
        weight = np.ones([2, ntimes, nlats, nlons, nmodels]) / nmodels

    if args.ctech == 'wpdf':
        prob_terc_comb = np.nansum(weight * prob_terciles, axis=4)

    elif args.ctech == 'wsereg':
        #ereg con el smme pesado
        weight = weight[0, :, :, :, :] / nmembers
        pronos_dt = np.rollaxis(for_dt * np.repeat(weight, nmembers, axis=3), 3, 1)
        [forecast_cr, Rmedio, Rmej, epsb, Kmax, K] = ereg.ensemble_regression(pronos_dt,
                                                                              obs_dt,
                                                                              True)
        #se calcula la media del ensamble (estas van a ser las predicciones determinísticas)
        message = f"Se van a calcular los datos determinísticos para datos en el archivo: {archivo}."
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        ensemble_mean = np.nanmean(forecast_cr, axis=1)
        message = f"Se calcularon los datos determinísticos para datos en el archivo: {archivo}."
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        #obtains prob for each terciles,year and member
        prob_terc = ereg.probabilidad_terciles(forecast_cr, epsb, terciles)
        #obtengo la combinacion a partir de la suma pesada
        prob_terc_comb = np.nanmean(prob_terc, axis=2)
    else:
        #calculo porcentaje de miembros que caen en cada categoria
        totalmembers = for_category.shape[4]
        for_category = np.sum(for_category, axis=4) / totalmembers
        #expreso el pronostico del mismo modo que con los otros dos metodos para que sea mas
        #sencillo verificar los pronos
        prob_terc_comb = np.cumsum(for_category, axis=0)[0:2, :, :, :]

    #guardo los pronos
    route = Path(PATH, cfg.get('folders').get('data').get('combined_forecasts'))
    if args.ctech == 'wsereg':
        archivo = args.variable[0] + '_mme_' + calendar.month_abbr[args.IC[0]]\
                + '_' + SSS + '_gp_01_' + args.wtech[0] + '_' + args.ctech + \
                '_hind.npz'
    else:
        archivo = args.variable[0] + '_mme_' + calendar.month_abbr[args.IC[0]]\
                + '_' + SSS + '_gp_01_' + args.wtech[0] + '_' + args.ctech + \
                '_hind.npz'

    np.savez(Path(route, archivo), prob_terc_comb=prob_terc_comb, lat=lat, lon=lon)
    cfg.set_correct_group_to_file(Path(route, archivo))  # Change group of file

    #guardo las predicciones determinísticas
    if args.ctech == 'wsereg' and cfg.get('gen_det_data', False):
        archivo_det = Path(PATH, cfg.get('folders').get('data').get('combined_forecasts'),
                           'determin_' + os.path.basename(archivo))
        message = f"Se van a guardar los datos determinísticos en el archivo: {archivo_det}."
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        np.savez(archivo_det, ensemble_mean=ensemble_mean, lat=lat, lon=lon)
        cfg.set_correct_group_to_file(archivo_det)  # Change group of file
        message = f"Se guardaron los datos determinísticos en el archivo: {archivo_det}."
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)


# ==================================================================================================
if __name__ == "__main__":
    
    # Defines parser data
    parser = argparse.ArgumentParser(description='Combining models')
    parser.add_argument('variable', type=str, nargs=1, 
        help='Variable to calibrate (prec or tref)')
    parser.add_argument('IC', type=int, nargs=1, 
        help='Month of initial conditions (from 1 for Jan to 12 for Dec)')
    parser.add_argument('leadtime', type=int, nargs=1, 
        help='Forecast leadtime (in months, from 1 to 7)')
    parser.add_argument('--no-models', nargs='+', dest='no_models', default=[],
        choices=[item[0] for item in cfg.get('models')[1:]], 
        help='Models to be discarded')
        
    subparsers = parser.add_subparsers(help="Combination technique")
    
    wpdf_parser = subparsers.add_parser('wpdf', help='weighted sum of calibrated PDFs')
    wsereg_parser = subparsers.add_parser('wsereg', help='Ereg with the weighted superensemble')
    count_parser = subparsers.add_parser('count', help='Count members in each bin')
    
    wpdf_parser.set_defaults(ctech='wpdf')
    wpdf_parser.add_argument("--weight_tech", required=True, nargs=1, 
        choices=['pdf_int', 'mean_cor', 'same'], dest='wtech',
        help='')
    wsereg_parser.set_defaults(ctech='wsereg')
    wsereg_parser.add_argument("--weight_tech", required=True, nargs=1, dest='wtech', 
        choices=['pdf_int', 'mean_cor', 'same'], 
        help='Relative weight between models')
    count_parser.set_defaults(ctech='count')
    count_parser.add_argument("--weight_tech", required=False, nargs=1, dest='wtech', 
        choices=['same'], default=['same'],
        help='Relative weight between models')
    
    # Extract data from args
    args = parser.parse_args()

    # Set error as not detected
    error_detected = False
  
    # Run combination
    start = time.time()
    try:
        main(args)
    except Exception as e:
        error_detected = True
        cfg.logger.error(f"Failed to run \"combination.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"combination.py\" ({err_pfx} errors): {end - start}" 
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

