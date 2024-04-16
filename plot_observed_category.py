# grafico pronostico
import argparse  # para hacer el llamado desde consola
import time
import calendar
import numpy as np
import xarray as xr
import matplotlib as mpl
from matplotlib import pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature
from pathlib import Path
import configuration
from plot_common_functions import manipular_nc

cfg = configuration.Config.Instance()

def main(args):
    """Plot observed category"""

    PATH = cfg.get('folders').get('download_folder')
    lsmask = Path(PATH, cfg.get('folders').get('nmme').get('root'), 'lsmask.nc')
    coords = cfg.get('coords')
    [land, Y, X] = manipular_nc(lsmask, "land", "Y", "X", coords['lat_n'],
                                coords['lat_s'], coords['lon_w'],
                                coords['lon_e'])
    land = np.flipud(land)
    #defino ref dataset y target season
    seas = range(args.IC[0], args.IC[0] + 3)
    sss = [i-12 if i>12 else i for i in seas]
    year_verif = 1991 if (seas[0] > 1 and seas[0] < 11) else 1992
    year_end = year_verif + 29
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)
    #obtengo datos observados
    PATH = cfg.get('folders').get('gen_data_folder')
    RUTA = Path(PATH, cfg.get('folders').get('data').get('observations'))
    RUTA_FIG = Path(PATH, cfg.get('folders').get('figures').get('observations'))
    archivo = 'obs_' + args.variable[0] + '_' + str(year_verif) + '_' + SSS + '.npz'
    data = np.load(Path(RUTA, archivo))
    obs_terciles = data['cat_obs']
    nlats = obs_terciles.shape[2]
    nlons = obs_terciles.shape[3]
    lat = data['lats_obs']
    lon = data['lons_obs']
    obs = np.zeros([nlats, nlons])
    lats = np.min(lat)
    latn = np.max(lat)
    lonw = np.min(lon)
    lone = np.max(lon)
    limits = [lonw, lone, lats, latn]
    [dx,dy] = np.meshgrid(lon,lat)
    if args.variable[0] == 'prec':
        cmap = mpl.colors.ListedColormap(np.array([[217, 95, 14], [189, 189, 189],
                                                   [44, 162, 95]]) / 256)
    else:
        cmap = mpl.colors.ListedColormap(np.array([[8., 81., 156.], [189, 189, 189],
                                                   [165., 15., 21.]]) / 256)

    for k in np.arange(year_verif, year_end + 1):
        output = Path(RUTA_FIG, 'obs_' + args.variable[0] + '_' + SSS + '_' + str(k) + '.png')
        obs_cat = obs_terciles[:, k - year_verif, :, :]
        obs[obs_cat[1, :, :] == 1] = 1
        obs[obs_cat[2, :, :] == 1] = 2
        obs[obs_cat[0, :, :] == 1] = 0
        obs = np.ma.masked_array(obs, np.logical_not(land.astype(bool)))
        fig = plt.figure()
        mapproj = ccrs.PlateCarree(central_longitude=(lonw + lone) /2)
        ax = plt.axes(projection=mapproj)
        ax.set_extent(limits, crs=ccrs.PlateCarree())
        ax.coastlines(alpha=0.5, resolution='50m')
        ax.add_feature(cartopy.feature.BORDERS, linestyle='-', alpha=0.5)
        CS1 = ax.pcolor(dx, dy, obs, cmap=cmap, alpha=0.6,
                             vmin=-0.5, vmax=2.5, transform=ccrs.PlateCarree())
        plt.title(SSS + " " + args.variable[0] + ' Observed Category - ' + str(k))
        ax = fig.add_axes([0.42, 0.05, 0.2, 0.03])
        bounds = [-0.5, 0.5, 1.5, 2.5]
        norm = mpl.colors.BoundaryNorm(bounds, cmap.N)
        cb = mpl.colorbar.ColorbarBase(ax, cmap=cmap, norm=norm,
                                       boundaries=bounds, ticks=[0, 1, 2],
                                       spacing='uniform',
                                       orientation='horizontal', alpha=0.6)
        cb.set_ticklabels(['Lower', 'Middle', 'Upper'])
        cb.ax.tick_params(labelsize=7)
        plt.savefig(output, dpi=600, bbox_inches='tight')  #, papertype='A4')  # papertype ya no es un param válido
        plt.close()
        cfg.set_correct_group_to_file(output)  # Change group of file


# ==================================================================================================
if __name__ == "__main__":
  
    # Define parser data
    parser = argparse.ArgumentParser(description='Plot observed category')
    parser.add_argument('variable',type=str, nargs=1,\
            help='Variable to verify (prec or tref)')
    parser.add_argument('IC', type=int, nargs=1,\
            help='Month of beginning of season (from 1 for Jan to 12 for Dec)')
    
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
        cfg.logger.error(f"Failed to run \"plot_observed_category.py\". Error: {e}.")
        raise
    else:
        error_detected = False
    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"plot_observed_category.py\" ({err_pfx} errors): {end - start}" 
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)

