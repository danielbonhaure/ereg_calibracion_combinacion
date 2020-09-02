#grafico pronostico
import argparse #para hacer el llamado desde consola
import time
import calendar
import numpy as np
import xarray as xr
import matplotlib as mpl
from matplotlib import pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature

def manipular_nc(archivo, variable, lat_name, lon_name, lats, latn, lonw, lone):
    """gets netdf variables"""
    dataset = xr.open_dataset(archivo, decode_times=False)
    var_out = dataset[variable].sel(**{lat_name: slice(lats, latn), lon_name: slice(lonw, lone)})
    lon = dataset[lon_name].sel(**{lon_name: slice(lonw, lone)})
    lat = dataset[lat_name].sel(**{lat_name: slice(lats, latn)})
    return var_out, lat, lon

def main():
    """Plot observed category"""
    # Define parser data
    parser = argparse.ArgumentParser(description='Plot observed category')
    parser.add_argument('variable',type=str, nargs=1,\
            help='Variable to verify (prec or temp)')
    parser.add_argument('IC', type=int, nargs=1,\
            help='Month of beginning of season (from 1 for Jan to 12 for Dec)')
    args=parser.parse_args()

    file1 = open("configuracion", 'r')
    PATH = file1.readline().rstrip('\n')
    file1.close()
    lsmask = PATH + "NMME/lsmask.nc"
    coordenadas = 'coords'
    domain = [line.rstrip('\n') for line in open(coordenadas)]  #Get domain limits
    coords = {'lat_s': float(domain[1]),
              'lat_n': float(domain[2]),
              'lon_w': float(domain[3]),
              'lon_e': float(domain[4])}
    [land, Y, X] = manipular_nc(lsmask, "land", "Y", "X", coords['lat_n'],
                                coords['lat_s'], coords['lon_w'],
                                coords['lon_e'])
    land = np.flipud(land)
    #defino ref dataset y target season
    seas = range(args.IC[0], args.IC[0] + 3)
    sss = [i-12 if i>12 else i for i in seas]
    year_verif = 1982 if (seas[0] > 1 and seas[0] < 11) else 1983
    SSS = "".join(calendar.month_abbr[i][0] for i in sss)
    #obtengo datos observados
    RUTA = PATH + 'DATA/Observations/'
    RUTA_FIG = PATH + 'FIGURES/'
    archivo = 'obs_' + args.variable[0] + '_' + str(year_verif) + '_' + SSS +\
            '.npz'
    data = np.load(RUTA + archivo)
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

    for k in np.arange(year_verif, 2011):
        output = RUTA_FIG + 'obs_' + args.variable[0] + '_' + SSS + '_' + str(k)\
                + '.png'
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
        plt.savefig(output, dpi=600, bbox_inches='tight', papertype='A4')
        plt.close()
#==========================================================================
start = time.time()
main()
end = time.time()
print(end - start)
