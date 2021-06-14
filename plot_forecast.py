"""smoth calibrated probabilities using a gaussian filter and plot forecast"""
import argparse  # parse command line options
import time  # test time consummed
import calendar
import numpy as np
import xarray as xr
import scipy.ndimage as ndimage
from astropy.io import fits
from astropy.utils.data import get_pkg_data_filename
from astropy.convolution import Gaussian2DKernel
from astropy.convolution import convolve
import matplotlib as mpl
mpl.use('agg')
from matplotlib import pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature
from pathlib import Path
import configuration

cfg = configuration.Config.Instance()

def manipular_nc(archivo, variable, lat_name, lon_name, lats, latn, lonw, lone):
    """gets netdf variables"""
    #reportar lectura de un archivo descargado
    cfg.report_input_file_used(archivo)
    #continuar ejecución
    dataset = xr.open_dataset(archivo, decode_times=False)
    var_out = dataset[variable].sel(**{lat_name: slice(lats, latn), lon_name: slice(lonw, lone)})
    lon = dataset[lon_name].sel(**{lon_name: slice(lonw, lone)})
    lat = dataset[lat_name].sel(**{lat_name: slice(lats, latn)})
    return var_out, lat, lon

def asignar_categoria(for_terciles):
    """determines most likely category"""
    most_likely_cat = np.argmax(for_terciles, axis=2)
    [nlats, nlons] = for_terciles.shape[0:2]
    for_cat = np.zeros([nlats, nlons], dtype=int)
    for_cat.fill(np.nan)
    for ii in np.arange(nlats):
        for jj in np.arange(nlons):
            if (most_likely_cat[ii, jj] == 2):
                if for_terciles[ii, jj, 2] >= 0.7:
                    for_cat[ii, jj] = 12
                elif for_terciles[ii, jj, 2] >= 0.6:
                    for_cat[ii, jj] = 11
                elif for_terciles[ii, jj, 2] >= 0.5:
                    for_cat[ii, jj] = 10
                elif for_terciles[ii, jj, 2] >= 0.4:
                    for_cat[ii, jj] = 9
            elif (most_likely_cat[ii, jj] == 0):
                if for_terciles[ii, jj, 0] >= 0.7:
                    for_cat[ii, jj] = 1
                elif for_terciles[ii, jj, 0] >= 0.6:
                    for_cat[ii, jj] = 2
                elif for_terciles[ii, jj, 0] >= 0.5:
                    for_cat[ii, jj] = 3
                elif for_terciles[ii, jj, 0] >= 0.4:
                    for_cat[ii, jj] = 4
            elif (most_likely_cat[ii, jj] == 1):
                if for_terciles[ii, jj, 1] >= 0.7:
                    for_cat[ii, jj] = 8
                elif for_terciles[ii, jj, 1] >= 0.6:
                    for_cat[ii, jj] = 7
                elif for_terciles[ii, jj, 1] >= 0.5:
                    for_cat[ii, jj] = 6
                elif for_terciles[ii, jj, 1] >= 0.4:
                    for_cat[ii, jj] = 5

            mascara = for_cat < 1
            for_mask = np.ma.masked_array(for_cat, mascara)
    return for_mask
    
def plot_pronosticos(pronos, dx, dy, lats, latn, lonw, lone, cmap, colores,
                     titulo, salida):
    """Plot probabilistic forecast"""
    limits = [lonw, lone, lats, latn]
    fig = plt.figure()
    mapproj = ccrs.PlateCarree(central_longitude=(lonw + lone) / 2)
    ax = plt.axes(projection=mapproj)
    ax.set_extent(limits, crs=ccrs.PlateCarree())
    ax.coastlines(alpha=0.5, resolution='50m')
    ax.add_feature(cartopy.feature.BORDERS, linestyle='-', alpha=0.5)
    CS1 = ax.pcolor(dx, dy, pronos, cmap=cmap, vmin=0.5, vmax=12.5,
                    transform=ccrs.PlateCarree())
    #genero colorbar para pronos
    plt.title(titulo)
    ax1 = fig.add_axes([0.2, 0.05, 0.2, 0.03])
    cmap1 = mpl.colors.ListedColormap(colores[0:4, :])
    bounds = [0.5, 1.5, 2.5, 3.5, 4.5]
    norm = mpl.colors.BoundaryNorm(bounds, cmap1.N)
    cb1 = mpl.colorbar.ColorbarBase(ax1, cmap=cmap1, norm=norm, boundaries=bounds,
                                    ticks=[1, 2, 3, 4], spacing='uniform',
                                    orientation='horizontal')
    cb1.set_ticklabels(['+70%', '65%', '55%', '45%'])
    cb1.ax.tick_params(labelsize=7)
    cb1.set_label('Lower')
    ax2 = fig.add_axes([0.415, 0.05, 0.2, 0.03])
    cmap2 = mpl.colors.ListedColormap(colores[4:8, :])
    bounds = [4.5, 5.5, 6.5, 7.5, 8.5]
    norm = mpl.colors.BoundaryNorm(bounds, cmap1.N)
    cb2 = mpl.colorbar.ColorbarBase(ax2, cmap=cmap2, norm=norm, boundaries=bounds,
                                    ticks=[5, 6, 7, 8], spacing='uniform',
                                    orientation='horizontal')
    cb2.set_ticklabels(['45%', '55%', '65%', '+70%'])
    cb2.ax.tick_params(labelsize=7)
    cb2.set_label('Normal')
    ax3 = fig.add_axes([0.63, 0.05, 0.2, 0.03])
    cmap3 = mpl.colors.ListedColormap(colores[8:, :])
    bounds = [8.5, 9.5, 10.5, 11.5, 12.5]
    norm = mpl.colors.BoundaryNorm(bounds, cmap1.N)
    cb3 = mpl.colorbar.ColorbarBase(ax3, cmap=cmap3, norm=norm, boundaries=bounds,
                                    ticks=[9, 10, 11, 12], spacing='uniform',
                                    orientation='horizontal')
    cb3.set_ticklabels(['45%', '55%', '65%', '+70%'])
    cb3.ax.tick_params(labelsize=7)
    cb3.set_label('Upper')
    plt.savefig(salida, dpi=600, bbox_inches='tight', papertype='A4')
    plt.close()
    cfg.set_correct_group_to_file(salida)  # Change group of file
    return

def main(args):
    # Defino ref dataset y target season
    seas = range(args.IC[0] + args.leadtime[0], args.IC[0] + args.leadtime[0] + 3)
    sss = [i - 12 if i > 12 else i for i in seas]
    year_verif = 1982 if seas[-1] <= 12 else 1983
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)
    month= calendar.month_abbr[args.IC[0]]
    wtech = ['pdf_int', 'mean_cor', 'same']
    ctech = ['wpdf', 'wsereg']
    #custom colorbar
    if args.variable[0] == 'prec':
        colores = np.array([[166., 54., 3.], [230., 85., 13.], [253., 141., 60.],
                            [253., 190., 133.], [227., 227., 227.], [204., 204.,
                                                                     204.],
                            [150., 150., 150.], [82., 82., 82.], [186., 228.,
                                                                  179.],
                            [116., 196., 118.], [49., 163., 84.], [0., 109.,
                                                                   44.]]) / 255
    else:
        colores = np.array([[8., 81., 156.], [49., 130., 189.],
                            [107., 174., 214.], [189., 215., 231.],
                            [227., 227., 227.], [204., 204., 204.],
                            [150., 150., 150.], [82., 82., 82.],
                            [252., 174., 145.], [251., 106., 74.],
                            [222., 45., 38.], [165., 15., 21.]]) / 255
    cmap = mpl.colors.ListedColormap(colores)
    #open and handle land-sea mask
    PATH = cfg.get('folders').get('download_folder')
    lsmask = Parth(PATH, cfg.get('folders').get('nmme').get('root'), 'lsmask.nc')
    coords = cfg.get('coords')
    [land, Y, X] = manipular_nc(lsmask, "land", "Y", "X", coords['lat_n'],
                                coords['lat_s'], coords['lon_w'],
                                coords['lon_e'])
    land = np.flipud(land)
    RUTA = Parth(PATH, cfg.get('folders').get('data').get('combined_forecasts'))
    RUTA_IM = Parth(PATH, cfg.get('folders').get('figures').get('combined_forecasts'))
    for i in ctech:
        for j in wtech:
            archivo = args.variable[0] + '_mme_' + month +'_' + \
                    SSS + '_gp_01_' + j + '_' + i + '_hind.npz'
            data = np.load(RUTA + archivo)
            lat = data['lat']
            lon = data['lon']
            lats = np.min(lat)
            latn = np.max(lat)
            lonw = np.min(lon)
            lone = np.max(lon)
            [dx, dy] = np.meshgrid(lon, lat)
            for k in np.arange(year_verif, 2011, 1):
                output = Path(RUTA_IM, 'for_' + args.variable[0] + '_' + SSS + '_ic_' +
                              month + '_' + str(k) + '_' + i + '_' + j + '.png')
                for_terciles = np.squeeze(data['prob_terc_comb'][:, k - 1982, :, :])
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
                                 cmap, colores, SSS + ' Forecast IC ' +\
                                 month + '-' + str(k) + ' - ' + i + '-' + j, output)

    archivo = args.variable[0] + '_mme_' + month + '_' + SSS + '_gp_01_same_count_hind.npz'
    data = np.load(Path(RUTA, archivo))
    lat = data['lat']
    lon = data['lon']
    lats = np.min(lat)
    latn = np.max(lat)
    lonw = np.min(lon)
    lone = np.max(lon)
    [dx, dy] = np.meshgrid (lon, lat)
    for k in np.arange(1982, 2011, 1):
        output = Path(RUTA_IM, 'for_' + args.variable[0] + '_' + SSS + '_ic_' + month + '_' + str(k) + '_count.png')
        for_terciles = np.squeeze(data['prob_terc_comb'][:, k-1982, :, :])
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
                                 cmap, colores, SSS + ' Forecast IC ' +\
                         month + '-' + str(k) +\
                         ' - Uncalibrated', output)


# ==================================================================================================
if __name__ == "__main__":
    
    # Define parser data
    parser = argparse.ArgumentParser(description='Verify combined forecast')
    parser.add_argument('variable',type=str, nargs= 1,\
            help='Variable to verify (prec or tref)')
    parser.add_argument('IC', type=int, nargs=1,\
            help='Month of intial conditions (from 1 for Jan to 12 for Dec)')
    parser.add_argument('leadtime', type=int, nargs=1,\
            help='Forecast leatime (in months, from 1 to 7)')
    
    # Extract data from args
    args = parser.parse_args()
  
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

