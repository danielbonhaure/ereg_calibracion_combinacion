"""smoth calibrated probabilities using a gaussian filter and plot forecast"""
import argparse  # parse command line options
import time  # test time consummed
import calendar
import datetime
import numpy as np
import xarray as xr
import scipy.ndimage as ndimage
from astropy.convolution import Gaussian2DKernel
from astropy.convolution import convolve
import matplotlib as mpl
from pathlib import Path
import configuration
from plot_common_functions import manipular_nc
from plot_common_functions import asignar_categoria_sissa as asignar_categoria
from plot_common_functions import plot_pronosticos_sissa as plot_pronosticos

cfg = configuration.Config.Instance()

def main(args):
    # Defino ref dataset y target season
    initialDate = datetime.datetime.strptime(args.IC[0], '%Y-%m-%d')
    iniy = initialDate.year
    inim = initialDate.month
    INIM = calendar.month_abbr[inim]
    seas = range(inim + args.leadtime[0], inim + args.leadtime[0] + 3)
    sss = [i - 12 if i > 12 else i for i in seas]
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)

    wtech = args.weighting  # ['mean_cor']
    ctech = args.combination  # ['wsereg']

    if 'wsereg' not in ctech:
        message = f"weightings not implemented - only wsereg"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        return
    if 'mean_cor' not in wtech:
        message = f"combinations not implemented - only mean_cor"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        return

    #custom colorbar
    for pp in ['quintiles', 'terciles']:
        if pp == 'quintiles':
            bounds = np.arange(10, 90, 10)
            prob_low = '20%'
            prob_high = '80%'
            nombres = '_extremes_mme_'
            sub_var = 'prob_quint_comb'
        else:
            bounds= [0, 33, 50, 66, 100]
            prob_low = '33%'
            prob_high = '66%'
            nombres = '_mme_'
            sub_var = 'prob_terc_comb'

        if args.variable[0] == 'prec':
            colores_above = mpl.cm.Greens
            colores_below = mpl.cm.Oranges
            # bounds = np.arange(10, 90, 10)
            PATH = cfg.get('folders').get('gen_data_folder')
            drymask = Path(PATH, cfg.get('folders').get('data').get('root'), 'dry_mask.nc')
            dms = xr.open_dataset(drymask)
            #selecciono mascara del mes
            dms = dms.sel(month=sss[1])

        else:
            colores_above = mpl.cm.Reds
            colores_below = mpl.cm.Blues
            # bounds = np.arange(10, 90, 10)
        #open and handle land-sea mask
        PATH = cfg.get('folders').get('download_folder')
        lsmask = Path(PATH, cfg.get('folders').get('nmme').get('root'), 'lsmask.nc')
        coords = cfg.get('coords')
        [land, Y, X] = manipular_nc(lsmask, "land", "Y", "X", coords['lat_n'],
                                    coords['lat_s'], coords['lon_w'],
                                    coords['lon_e'])
        land = np.flipud(land)
        PATH = cfg.get('folders').get('gen_data_folder')
        RUTA = Path(PATH, cfg.get('folders').get('data').get('real_time_forecasts'))
        RUTA_IM = Path(PATH, cfg.get('folders').get('figures').get('real_time_forecasts'))
        for i in ctech:
            if i != 'wsereg':
                continue
            for j in wtech:
                if j != 'mean_cor':
                    continue
                archivo = Path(RUTA, args.variable[0] + nombres + INIM + str(iniy)\
                               + '_' + SSS + '_gp_01_' + j + '_' + i + '.npz')
                data = np.load(archivo)
                lat = data['lat']
                lon = data['lon']
                lats = np.min(lat)
                latn = np.max(lat)
                lonw = np.min(lon)
                lone = np.max(lon)
                [dx, dy] = np.meshgrid(lon, lat)

                for_terciles = np.squeeze(data[sub_var][:, :, :])
                #agrego el prono de la categoria above normal
                if args.variable[0] == 'prec':
                    below = ndimage.gaussian_filter(for_terciles[0, :, :], 1,
                                                    order=0, output=None,
                                                    mode='constant')
                    near = ndimage.gaussian_filter(for_terciles[1, :, :], 1,
                                                   order=0, output=None,
                                                   mode='constant')
                else:
                    for_terciles[:, for_terciles[1, :, :] == 0] = np.nan
                    kernel = Gaussian2DKernel(x_stddev=1)
                    below = convolve(for_terciles[0, :, :], kernel, preserve_nan=True)
                    near = convolve(for_terciles[1, :, :], kernel, preserve_nan=True)
                above = 1 - near
                near = near - below
                for_terciles = np.concatenate([below[:, :, np.newaxis],
                                               near[:, :, np.newaxis],
                                               above[:, :, np.newaxis]], axis=2)
                ### Modificado M
                message = f"max: {np.nanmax(for_terciles)}, min: {np.nanmin(for_terciles)}"
                print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
                ###
                for_mask = asignar_categoria(for_terciles)
                
                if args.variable[0] =='prec':
                    for_mask[dms.prec.values, :] = 0
                    # plot below
                    output = Path(RUTA_IM, 'for_' + args.variable[0] + '_low' + prob_low + '_' + SSS + '_ic_' +
                                  INIM + '_' + str(iniy) + '.png')

                    plot_pronosticos(np.ma.masked_array(for_mask[:, :, 0],
                                                        np.logical_not(land.astype(bool))),
                                     dx, dy, lats, latn, lonw, lone,
                                     colores_below,
                                     mpl.colors.BoundaryNorm(bounds, colores_below.N), 
                                     SSS + ' ' + args.variable[0] +\
                                     ' below ' + prob_low + ' hist range -  Forecast IC ' + INIM + ' ' + str(iniy),
                                     output)

                    output = Path(RUTA_IM, 'for_' + args.variable[0] + '_high' + prob_high + '_' + SSS + '_ic_' +
                                  INIM + '_' + str(iniy) + '.png')

                    plot_pronosticos(np.ma.masked_array(for_mask[:, :, 2],
                                                        np.logical_not(land.astype(bool))),
                                     dx, dy, lats, latn, lonw, lone,
                                     colores_above,
                                     mpl.colors.BoundaryNorm(bounds, colores_above.N), 
                                     SSS + ' ' + args.variable[0] +\
                                     ' above ' + prob_high + ' hist range -  Forecast IC ' + INIM + ' ' + str(iniy),
                                     output)

                else:
                    output = Path(RUTA_IM, 'for_' + args.variable[0] + '_high' + prob_high + '_' + SSS + '_ic_' +
                                  INIM + '_' + str(iniy) + '.png')

                    plot_pronosticos(np.ma.masked_array(for_mask[:, :, 2],
                                                        np.logical_not(land.astype(bool))),
                                     dx, dy, lats, latn, lonw, lone,
                                     colores_above,
                                     mpl.colors.BoundaryNorm(bounds, colores_above.N), 
                                     SSS + ' ' + args.variable[0] +\
                                     ' above ' + prob_high + ' hist range -  Forecast IC ' + INIM + ' ' + str(iniy),
                                     output)

                    output = Path(RUTA_IM, 'for_' + args.variable[0] + '_low' + prob_low + '_' + SSS + '_ic_' +
                                  INIM + '_' + str(iniy) + '.png')

                    plot_pronosticos(np.ma.masked_array(for_mask[:, :, 0],
                                                        np.logical_not(land.astype(bool))),
                                     dx, dy, lats, latn, lonw, lone,
                                     colores_below,
                                     mpl.colors.BoundaryNorm(bounds, colores_below.N), 
                                     SSS + ' ' + args.variable[0] +\
                                     ' below ' + prob_low + ' hist range -  Forecast IC ' + INIM + ' ' + str(iniy),
                                     output)


# ==================================================================================================
if __name__ == "__main__":
  
    # Define parser data
    parser = argparse.ArgumentParser(description='Verify combined forecast')
    parser.add_argument('variable',type=str, nargs= 1,\
            help='Variable to verify (prec or tref)')
    parser.add_argument('--IC', type=str, nargs=1,\
            help='Date of initial conditions (in "YYYY-MM-DD")')
    parser.add_argument('--leadtime', type=int, nargs=1,\
            help='Forecast leadtime (in months, from 1 to 7)')
    parser.add_argument('--weighting', nargs='+',
            default=["mean_cor"], choices=["same", "pdf_int", "mean_cor"],
            help='Weighting methods to be plotted.')
    parser.add_argument('--combination', nargs='+',
            default=["wsereg"], choices=["wpdf", "wsereg"],
            help='Combination methods to be plotted.')

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
        cfg.logger.error(f"Failed to run \"plot_sissa_forecast.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"plot_sissa_forecast.py\" ({err_pfx} errors): {end - start}"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
