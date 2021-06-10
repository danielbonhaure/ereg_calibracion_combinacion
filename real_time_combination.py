"""
real time forecast using combination techniques developedin combination.py
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
    
    initialDate = datetime.datetime.strptime(args.IC[0], '%Y-%m-%d')
    iniy = initialDate.year
    inim = initialDate.month
    
    coords = cfg.get('coords')
    conf_modelos = cfg.get('models')
    
    df_modelos = pd.DataFrame(conf_modelos[1:], columns=conf_modelos[0])
    
    if args.no_models:  # si hay que descartar algunos modelos
        df_modelos = df_modelos.query(f"model not in {args.no_models}")
        
    keys = ['nombre', 'instit', 'latn', 'lonn', 'miembros', 'plazos',\
            'fechai', 'fechaf','ext', 'rt_miembros']
    df_modelos.columns = keys
    
    modelos = df_modelos.to_dict('records')
    
    nmodels = len(modelos)
    ny = int(np.abs(coords['lat_n'] - coords['lat_s']) + 1)
    nx = int(np.abs (coords['lon_e'] - coords['lon_w']) + 1) #does for domains beyond greenwich
    nyears = int(modelos[0]['fechaf'] - modelos[0]['fechai'] + 1)
    if args.ctech == 'wpdf':
        prob_terciles = np.array([]).reshape(2, ny, nx, 0)
    elif args.ctech == 'wsereg':
        for_dt = np.array([]).reshape(nyears, ny, nx, 0) #[years lats lons members]
        prono_actual_dt = np.array([]).reshape(ny, nx, 0) #[lats lons members]
    if args.wtech[0] == 'pdf_int':
        weight = np.array([]).reshape(nyears, ny, nx, 0)
    elif args.wtech[0] == 'mean_cor':
        rmean = np.array([]).reshape(ny, nx, 0)
    nmembers = np.empty([nmodels], dtype=int)
    #defino ref dataset y target season
    seas = range(inim + args.leadtime[0], inim + args.leadtime[0] + 3)
    sss = [i - 12 if i > 12 else i for i in seas]
    year_verif = 1982 if seas[-1] <= 12 else 1983
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)
    message = 'Var:' + args.variable[0] + ' IC:' + calendar.month_abbr[inim] +\
              ' Target season:' + SSS + ' ' + args.ctech + ' ' + args.wtech[0]
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
    #obtengo datos observados
    archivo = Path(f'{cfg.get("gen_data_folder")}/nmme_output/obs_'.replace('//','/') +\
                   args.variable[0] + '_' + str(year_verif) + '_' + SSS + '_parameters.npz')
    data = np.load(archivo)
    terciles = data['terciles']
    if args.ctech == 'wsereg':
        obs_dt = data['obs_dt']
    j = 0
    for it in modelos:
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
        #abro archivo modelo
        archivo = Path(f'{cfg.get("gen_data_folder")}/nmme_output'.replace('//','/') +\
                       '/cal_forecasts/' + args.variable[0] + '_' + it['nombre'] + '_' +\
                       calendar.month_abbr[inim] + '_' + SSS + '_gp_01_hind_parameters.npz')
        data = np.load(archivo)
        a1 = data['a1']
        b1 = data['b1']
        #remove trend
        T = iniy - 1982
        f_dt = pronos - (b1 + T * a1)
        if args.ctech == 'wpdf':
            a2 = data['a2']
            b2 = data['b2']
            K = data['K'][0, :, :, :]
            eps = data['eps']
            f_dt = f_dt * K + (1 - K) * np.mean(f_dt, axis = 0)
            for_cr = b2 + f_dt * a2
            #integro en los limites de terciles
            prob_terc = modelo.probabilidad_terciles(for_cr, eps, terciles)
            prob_terc = np.nanmean(prob_terc, axis=1)
            #junto todos pronos calibrados
            prob_terciles = np.concatenate((prob_terciles,
                                            prob_terc[:, :, :, np.newaxis]),
                                           axis=3)
        elif args.ctech == 'wsereg':
            #junto pronos actual
            prono_actual_dt = np.concatenate((prono_actual_dt,
                                              np.rollaxis(f_dt, 0, 3)), axis=2)
            f_dt = []
            #junto pronos hindcast
            f_dt = data['pronos_dt']
            nmembers[j] = np.shape(f_dt)[1]
            for_dt = np.concatenate((for_dt, np.rollaxis(f_dt, 1, 4)), axis=3)
        #extraigo info del peso segun la opcion por la que elijo pesar
        if args.wtech[0] == 'pdf_int':
            peso = data['peso']
            ### Modificado M
            # weight = np.concatenate((weight, peso[:, 0, :, :][:, :, :,
            #                                                   np.newaxis]),
            #                         axis=3)
            weight = np.concatenate((weight, peso[:, :, :][:, :, :,
                                                           np.newaxis]),
                                    axis=3)
            ###
            peso = []
        elif args.wtech[0] == 'mean_cor':
            Rm = data['Rm']
            rmean = np.concatenate((rmean, Rm[:, :, np.newaxis]), axis=2)
            Rm = []
        j = j + 1

    lat = lats
    lon = lons
    nlats = np.shape(lat)[0]
    nlons = np.shape(lon)[0]

  #calculo matriz de peso
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
        rmean[np.where(np.logical_and(rmean < 0, ~np.isnan(rmean)))] = 0
        rmean[np.nansum(rmean[:, :, :], axis=2) == 0, :] = 1
        peso = rmean / np.tile(np.nansum(rmean, axis=2)[:, :, np.newaxis], [1, 1, nmodels])
        weight = np.tile(peso, (2, 1, 1, 1))  #2 nlat nlon nmodels

    elif args.wtech[0] == 'same': #mismo peso para todos
        weight = np.ones([2, nlats, nlons, nmodels]) / nmodels

    if args.ctech == 'wpdf':
        prob_terc_comb = np.nansum(weight[:, :, :, :] * prob_terciles, axis=3)
    elif args.ctech == 'wsereg':
        ntimes = np.shape(for_dt)[0]
        weight = np.tile(weight[0, :, :, :], (ntimes, 1, 1, 1)) / nmembers
        archivo = Path(f'{cfg.get("gen_data_folder")}/nmme_output'.replace('//','/') +\
                       '/comb_forecast/' + args.variable[0]+'_mme_' + calendar.month_abbr[inim] +\
                       '_' + SSS + '_gp_01_' + args.wtech[0]+'_' + args.ctech +\
                       '_hind_parameters.npz')
        if archivo.is_file() and not args.OW:
            data = np.load(archivo)
            a_mme = data['a_mme']
            b_mme = data['b_mme']
            eps_mme = data['eps_mme']
            K_mme = data['K_mme']
        else:
            #ereg con el smme pesado
            for_dt = np.rollaxis(for_dt * np.repeat(weight, nmembers, axis=3), 3, 1)
            [a_mme, b_mme, R_mme, Rb_mme, eps_mme, Kmax_mme,
             K_mme] = ereg.ensemble_regression(for_dt, obs_dt, False)
            np.savez(archivo, a_mme=a_mme, b_mme=b_mme, R_mme=R_mme,
                     Rb_mme=Rb_mme, eps_mme=eps_mme, Kmax_mme=Kmax_mme,
                     K_mme=K_mme)
            cfg.set_correct_group_to_file(archivo)  # Change group of file
        #peso prono actual
        prono_actual_dt = np.rollaxis(prono_actual_dt * np.repeat(weight[0, :, :, :],
                                                                  nmembers,
                                                                  axis=2),
                                      2, 0)
        K_mme = K_mme[0, :, :, :]
        prono_actual_dt = prono_actual_dt * K_mme + (1 - K_mme) *\
                np.nanmean(prono_actual_dt, axis = 0)
        #corrijo prono
        prono_cr = b_mme + a_mme * prono_actual_dt
        #obtains prob for each terciles,year and member
        prob_terc = ereg.probabilidad_terciles(prono_cr, eps_mme, terciles)
        prob_terc_comb = np.nanmean(prob_terc, axis=1)

    #guardo los pronos
    archivo = Path(f'{cfg.get("gen_data_folder")}/nmme_output'.replace('//','/') +\
                   '/rt_forecast/' + args.variable[0]+'_mme_' + calendar.month_abbr[inim] +\
                   str(iniy) + '_' + SSS + '_gp_01_' + args.wtech[0]+'_' +\
                   args.ctech + '.npz')
    np.savez(archivo, prob_terc_comb=prob_terc_comb, lat=lat, lon=lon)
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
    parser.add_argument('--OW', 
        help='Overwrite previous calibrations', action='store_true')
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
        help = '')
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
  
    # Run real time combination
    start = time.time()
    try:
        main(args)
    except Exception as e:
        error_detected = True
        cfg.logger.error(f"Failed to run \"real_time_combination.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"real_time_combination.py\" ({err_pfx} errors): {end - start}" 
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

