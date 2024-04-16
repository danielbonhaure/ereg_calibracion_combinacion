"""smoth calibrated probabilities using a gaussian filter and plot forecast"""
import argparse  # parse command line options
import time  # test time consummed
import calendar
import numpy as np
import scipy.ndimage as ndimage
from astropy.convolution import Gaussian2DKernel
from astropy.convolution import convolve
import matplotlib as mpl
from pathlib import Path
import configuration
from plot_common_functions import manipular_nc, asignar_categoria, plot_pronosticos

cfg = configuration.Config.Instance()

def main(args):
    # Defino ref dataset y target season
    seas = range(args.IC[0] + args.leadtime[0], args.IC[0] + args.leadtime[0] + 3)
    sss = [i - 12 if i > 12 else i for i in seas]
    year_verif = 1991 if seas[-1] <= 12 else 1992
    year_end = year_verif + 29
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)
    month= calendar.month_abbr[args.IC[0]]
    wtech = args.weighting  # ['pdf_int', 'mean_cor', 'same']
    ctech = args.combination  # ['wpdf', 'wsereg']
    #custom colorbar
    if args.variable[0] == 'prec':
        colores = np.array([[166., 54., 3.], [230., 85., 13.], [253., 141., 60.],
                            [253., 190., 133.], [227., 227., 227.], [204., 204.,
                                                                     204.],
                            [150., 150., 150.], [82., 82., 82.], [186., 228.,
                                                                  179.],
                            [116., 196., 118.], [49., 163., 84.], [0., 109.,
                                                                   44.]]) / 255
        vmin = 0.5
        vmax = 13.5
    else:
        colores = np.array([[8., 81., 156.], [49., 130., 189.],
                            [107., 174., 214.], [189., 215., 231.],
                            [227., 227., 227.], [204., 204., 204.],
                            [150., 150., 150.], [82., 82., 82.],
                            [252., 174., 145.], [251., 106., 74.],
                            [222., 45., 38.], [165., 15., 21.]]) / 255
        vmin = 0.5
        vmax = 12.5

    cmap = mpl.colors.ListedColormap(colores)
    #open and handle land-sea mask
    PATH = cfg.get('folders').get('download_folder')
    lsmask = Path(PATH, cfg.get('folders').get('nmme').get('root'), 'lsmask.nc')
    coords = cfg.get('coords')
    [land, Y, X] = manipular_nc(lsmask, "land", "Y", "X", coords['lat_n'],
                                coords['lat_s'], coords['lon_w'],
                                coords['lon_e'])
    land = np.flipud(land)
    PATH = cfg.get('folders').get('gen_data_folder')
    RUTA = Path(PATH, cfg.get('folders').get('data').get('combined_forecasts'))
    RUTA_IM = Path(PATH, cfg.get('folders').get('figures').get('combined_forecasts'))
    for i in ctech:
        for j in wtech:
            archivo = args.variable[0] + '_mme_' + month + '_' + \
                    SSS + '_gp_01_' + j + '_' + i + '_hind.npz'
            info_message = f'File: "{Path(RUTA, archivo)}".'
            print(info_message) if not cfg.get('use_logger') else cfg.logger.info(info_message)
            data = np.load(Path(RUTA, archivo))
            lat = data['lat']
            lon = data['lon']
            lats = np.min(lat)
            latn = np.max(lat)
            lonw = np.min(lon)
            lone = np.max(lon)
            [dx, dy] = np.meshgrid(lon, lat)
            for k in np.arange(year_verif, year_end + 1, 1):
                output = Path(RUTA_IM, 'for_' + args.variable[0] + '_' + SSS + '_ic_' +
                              month + '_' + str(k) + '_' + i + '_' + j + '.png')
                for_terciles = np.squeeze(data['prob_terc_comb'][:, k - year_verif, :, :])
                if args.variable[0] == 'prec':
                    #agrego el prono de la categoria above normal
                    below = ndimage.filters.gaussian_filter(for_terciles[0, :,
                                                                         :], 1,
                                                            order=0, output=None,
                                                            mode='reflect')

                    above = ndimage.filters.gaussian_filter(1 - for_terciles[1, :,
                                                                             :], 1,
                                                            order=0, output=None,
                                                            mode='reflect')
                else:
                    #for_terciles[0, np.logical_not(land.astype(bool))] = np.nan
                    for_terciles[:, np.logical_not(land.astype(bool))] = np.nan
                    #above = 1 - for_terciles[1, :, :]
                    #above[np.logical_not(land.astype(bool))] = np.nan
                    kernel = Gaussian2DKernel(x_stddev=1)
                    below = convolve(for_terciles[0, :, :], kernel)
                    #above = convolve(above, kernel)
                    above = 1 - convolve(for_terciles[1, :, :], kernel)
                near = 1 - below - above
                for_terciles = np.concatenate([below[:, :, np.newaxis],
                                               near[:, :, np.newaxis],
                                               above[:, :, np.newaxis]], axis=2)
                for_mask = asignar_categoria(for_terciles)
                for_mask = np.ma.masked_array(for_mask,
                                              np.logical_not(land.astype(bool)))
                plot_pronosticos(for_mask, dx, dy, lats, latn, lonw, lone,
                                 cmap, colores, vmin, vmax, SSS + ' Forecast IC ' +\
                                 month + '-' + str(k) + ' - ' + i + '-' + j, output)

    archivo = args.variable[0] + '_mme_' + month + '_' + SSS + '_gp_01_same_count_hind.npz'
    if not Path(RUTA, archivo).is_file():
        warn_message = f'No such file: "{archivo}". It will not be possible to build the uncalibrated forecast plot.'
        print(warn_message) if not cfg.get('use_logger') else cfg.logger.warning(warn_message)
        return
    data = np.load(Path(RUTA, archivo))
    lat = data['lat']
    lon = data['lon']
    lats = np.min(lat)
    latn = np.max(lat)
    lonw = np.min(lon)
    lone = np.max(lon)
    [dx, dy] = np.meshgrid (lon, lat)
    for k in np.arange(year_verif, year_end + 1, 1):
        output = Path(RUTA_IM, 'for_' + args.variable[0] + '_' + SSS + '_ic_' + month + '_' + str(k) + '_count.png')
        for_terciles = np.squeeze(data['prob_terc_comb'][:, k-year_verif, :, :])
        #agrego el prono de la categoria above normal
        for_terciles = np.concatenate([for_terciles[0, :, :][:, :, np.newaxis],
                                       (for_terciles[1, :, :] -
                                        for_terciles[0, :, :])[:, :,
                                                               np.newaxis],
                                       (1 - for_terciles[1, :, :])[:, :,
                                                                   np.newaxis]],
                                      axis=2)
        for_mask = asignar_categoria(for_terciles)
        for_mask = np.ma.masked_array(for_mask,
                                      np.logical_not(land.astype(bool)))
        plot_pronosticos(for_mask, dx, dy, lats, latn, lonw, lone,
                         cmap, colores, vmin, vmax, SSS + ' Forecast IC ' +\
                         month + '-' + str(k) +\
                         ' - Uncalibrated', output)


# ==================================================================================================
if __name__ == "__main__":

    # Define parser data
    parser = argparse.ArgumentParser(description='Verify combined forecast')
    parser.add_argument('variable',type=str, nargs= 1,\
            help='Variable to verify (prec or tref)')
    parser.add_argument('IC', type=int, nargs=1,\
            help='Month of initial conditions (from 1 for Jan to 12 for Dec)')
    parser.add_argument('leadtime', type=int, nargs=1,\
            help='Forecast leadtime (in months, from 1 to 7)')
    parser.add_argument('--weighting', nargs='+',
            default=["same", "pdf_int", "mean_cor"], choices=["same", "pdf_int", "mean_cor"],
            help='Weighting methods to be plotted.')
    parser.add_argument('--combination', nargs='+',
            default=["wpdf", "wsereg"], choices=["wpdf", "wsereg"],
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
        cfg.logger.error(f"Failed to run \"plot_forecast.py\". Error: {e}.")
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"plot_forecast.py\" ({err_pfx} errors): {end - start}" 
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

