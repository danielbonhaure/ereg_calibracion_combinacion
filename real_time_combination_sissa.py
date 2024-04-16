"""
real time forecast using combination techniques developedin combination.py
"""
#!/usr/bin/env python
import argparse  # parse command line options
import time  # test time consummed
import datetime
import warnings
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
    
    initialDate = datetime.datetime.strptime(args.IC[0], '%Y-%m-%d')
    iniy = initialDate.year
    inim = initialDate.month
    
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
    nyears = int(modelos[0]['fechaf'] - modelos[0]['fechai'] + 1)
    if args.ctech == 'wpdf':
        message = "wpdf not implemented - only wsereg"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        return
    elif args.ctech == 'wsereg':
        for_dt = np.array([]).reshape(nyears, ny, nx, 0) #[years lats lons members]
        prono_actual_dt = np.array([]).reshape(ny, nx, 0) #[lats lons members]
    if args.wtech[0] == 'pdf_int':
        message = "pdf_int not implemented - only mean_cor"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        return
    elif args.wtech[0] == 'mean_cor':
        rmean = np.array([]).reshape(ny, nx, 0)
    nmembers = []
    nmembersf = np.empty([nmodels], dtype=int)
    #defino ref dataset y target season
    seas = range(inim + args.leadtime[0], inim + args.leadtime[0] + 3)
    sss = [i - 12 if i > 12 else i for i in seas]
    year_verif = 1991 if seas[-1] <= 12 else 1991
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)
    message = 'Var:' + args.variable[0] + ' IC:' + calendar.month_abbr[inim] +\
              ' Target season:' + SSS + ' ' + args.ctech + ' ' + args.wtech[0]
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
    #obtengo datos observados
    archivo = Path(PATH, cfg.get('folders').get('data').get('observations'), 'obs_extremes_' + args.variable[0]+'_'+\
                   str(year_verif) + '_' + SSS + '_parameters.npz')
    data = np.load(archivo)
    quintiles = data['quintiles']
    j = 0
    for it in modelos:
        if np.logical_and(it['nombre'] == 'CFSv2', inim == 11): 
            modelo = model.Model(it['nombre'], it['instit'], args.variable[0],\
                            it['latn'], it['lonn'], it['miembros'] + 4, \
                            it['plazos'], it['fechai'], it['fechaf'],\
                            it['ext'], it['rt_miembros'] + 4)
        else:
            modelo = model.Model(it['nombre'], it['instit'], args.variable[0],\
                            it['latn'], it['lonn'], it['miembros'], \
                            it['plazos'], it['fechai'], it['fechaf'],\
                            it['ext'], it['rt_miembros'])

        message = f"Current model: {it['nombre']}"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        [lats, lons, pronos] = modelo.select_real_time_months(inim, iniy,\
                                                             args.leadtime[0],
                                                             coords['lat_s'],
                                                             coords['lat_n'],
                                                             coords['lon_w'],
                                                             coords['lon_e'])
        """
        #aca deberia meter codigo que: -marque los pronosticos que son nan. cuente cuantos son nan
        #saque el modelo si todos los pronos son nan y pase al siguiente modelo. Reduzca el tamaño
        de los modelos
        """
        empty_forecast = np.sum(np.sum(np.isnan(pronos), axis=2), axis=1) == (nx * ny) # modificado
        vacio = np.sum(empty_forecast) == pronos.shape[0]
        if not(vacio):
            #abro archivo modelo
            archivo = Path(PATH, cfg.get('folders').get('data').get('calibrated_forecasts'),
                           args.variable[0] + '_' + it['nombre'] + '_' +\
                           calendar.month_abbr[inim] + '_' + SSS +\
                           '_gp_01_hind_parameters.npz')
            data = np.load(archivo)
            a1 = data['a1']
            b1 = data['b1']
            #remove trend
            T = iniy - 1991
            f_dt = pronos - (b1 + T * a1)
            f_dt[empty_forecast, :, :] = np.nan # modificado
            #junto pronos actual
            prono_actual_dt = np.concatenate((prono_actual_dt,
                                              np.rollaxis(f_dt, 0, 3)), axis=2)
            nmembersf[j] = np.shape(f_dt)[0]
            nmembers.append(np.shape(f_dt)[0] - np.sum(empty_forecast)) # modificado
            #extraigo info del peso segun la opcion por la que elijo pesar
            Rm = data['Rm']
            rmean = np.concatenate((rmean, Rm[:, :, np.newaxis]), axis=2)
            Rm = []
        else:
            nmodels -= 1
        j = j + 1

    lat = lats
    lon = lons
    nlats = np.shape(lat)[0]
    nlons = np.shape(lon)[0]

    #calculo matriz de peso
    rmean[np.where(np.logical_or(rmean < 0, ~np.isfinite(rmean)))] = 0
    rmean[np.nansum(rmean[:, :, :], axis=2) == 0, :] = 1
    peso = rmean / np.tile(np.nansum(rmean, axis=2)[:, :, np.newaxis], [1, 1, nmodels])
    weight = np.tile(peso, (2, 1, 1, 1))  #2 nlat nlon nmodels

    weight = weight[0, :, :, :] / nmembers
    archivo = Path(PATH, cfg.get('folders').get('data').get('combined_forecasts'),
                   args.variable[0]+'_mme_' + calendar.month_abbr[inim] +\
                   '_' + SSS + '_gp_01_' + args.wtech[0]+'_' + args.ctech +\
                   '_hind_parameters.npz')
    data = np.load(archivo)
    a_mme = data['a_mme']
    b_mme = data['b_mme']
    eps_mme = data['eps_mme']
    K_mme = data['K_mme']
    #peso prono actual
    # check nans
    empty_forecast = np.sum(np.sum(np.isnan(prono_actual_dt), axis=1), axis=0) == (nx * ny) # modificado
    prono_actual_dt = np.rollaxis(prono_actual_dt * np.repeat(weight, nmembersf, axis=2),
                                  2, 0)
    K_mme = K_mme[0, :, :, :]
    prono_actual_dt[empty_forecast, :, :] = np.nan
    prono_actual_dt = prono_actual_dt * K_mme + (1 - K_mme) *\
            np.nanmean(prono_actual_dt, axis = 0)
    #corrijo prono
    prono_cr = b_mme + a_mme * prono_actual_dt
    #obtains prob for each terciles,year and member
    prob_quint = ereg.probabilidad_quintiles(prono_cr, eps_mme, quintiles)
    prob_quint[:, empty_forecast, :, :] = np.nan
    #empty forecast to nana
    prob_quint_comb = np.nanmean(prob_quint, axis=1)

    #guardo los pronos
    archivo = Path(PATH, cfg.get('folders').get('data').get('real_time_forecasts'),
                   args.variable[0]+'_extremes_mme_' + calendar.month_abbr[inim] +\
                   str(iniy) + '_' + SSS + '_gp_01_' + args.wtech[0]+'_' +\
                   args.ctech + '.npz')
    np.savez(archivo, prob_quint_comb=prob_quint_comb, lat=lat, lon=lon)
    cfg.set_correct_group_to_file(archivo)  # Change group of file


# ==================================================================================================
if __name__ == "__main__":
    
    # Defines parser data
    parser = argparse.ArgumentParser(description='Combining models')
    parser.add_argument('variable', type=str, nargs=1, 
        help='Variable to calibrate (prec or tref)')
    parser.add_argument('--IC', dest='IC', metavar='Date', type=str, nargs=1,
        help='Initial conditions in "YYYY-MM-DD"')
    parser.add_argument('--leadtime', dest='leadtime', type=int, nargs=1,
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
        help='Relative weight between models')
    wsereg_parser.set_defaults(ctech='wsereg')
    wsereg_parser.add_argument("--weight_tech", required=True, nargs=1, 
        choices=['pdf_int', 'mean_cor', 'same'], dest='wtech', 
        help='Relative weight between models')
    count_parser.set_defaults(ctech='count')
    count_parser.add_argument("--weight_tech", required=False, nargs=1, dest='wtech', 
        choices=['same'], default=['same'],
        help='Relative weight between models')
    
    # Extract data from args
    args = parser.parse_args()

    # Set error as not detected
    error_detected = False
  
    # Run real time combination
    start = time.time()
    try:
        main(args)
    except Exception as e:
        error_detected = True
        cfg.logger.error(f"Failed to run \"real_time_combination_sissa.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"real_time_combination_sissa.py\" ({err_pfx} errors): {end - start}"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

