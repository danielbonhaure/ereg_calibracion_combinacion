
from matplotlib import pyplot as plt

import numpy as np
import xarray as xr
import matplotlib as mpl
import cartopy.crs as ccrs
import cartopy.feature
import configuration
import os

mpl.use('agg')
cfg = configuration.Config.Instance()


def manipular_nc(archivo, variable, lat_name, lon_name, lats, latn, lonw, lone):
    """gets netdf variables"""
    # reportar lectura de un archivo descargado
    cfg.report_input_file_used(archivo)
    # continuar ejecución
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
            if most_likely_cat[ii, jj] == 2:
                if for_terciles[ii, jj, 2] >= 0.7:
                    for_cat[ii, jj] = 12
                elif for_terciles[ii, jj, 2] >= 0.6:
                    for_cat[ii, jj] = 11
                elif for_terciles[ii, jj, 2] >= 0.5:
                    for_cat[ii, jj] = 10
                elif for_terciles[ii, jj, 2] >= 0.4:
                    for_cat[ii, jj] = 9
            elif most_likely_cat[ii, jj] == 0:
                if for_terciles[ii, jj, 0] >= 0.7:
                    for_cat[ii, jj] = 1
                elif for_terciles[ii, jj, 0] >= 0.6:
                    for_cat[ii, jj] = 2
                elif for_terciles[ii, jj, 0] >= 0.5:
                    for_cat[ii, jj] = 3
                elif for_terciles[ii, jj, 0] >= 0.4:
                    for_cat[ii, jj] = 4
            elif most_likely_cat[ii, jj] == 1:
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


def asignar_categoria_sissa(for_terciles):
    """determines most likely category"""
    for_cat = for_terciles * 100
    mascara = for_cat < 10
    for_mask = np.ma.masked_array(for_cat, mascara)
    return for_mask


def plot_pronosticos(pronos, dx, dy, lats, latn, lonw, lone, cmap, colores, vmin, vmax,
                     titulo, salida):
    """Plot probabilistic forecast"""
    init_message = f"Generating figure: {os.path.basename(salida)}"
    print(init_message) if not cfg.get('use_logger') else cfg.logger.info(init_message)
    limits = [lonw, lone, lats, latn]
    fig = plt.figure()
    mapproj = ccrs.PlateCarree(central_longitude=(lonw + lone) / 2)
    ax = plt.axes(projection=mapproj)
    ax.set_extent(limits, crs=ccrs.PlateCarree())
    ax.coastlines(alpha=0.5, resolution='50m')
    ax.add_feature(cartopy.feature.BORDERS, linestyle='-', alpha=0.5)
    CS1 = ax.pcolor(dx, dy, pronos, cmap=cmap, vmin=vmin, vmax=vmax,
                    transform=ccrs.PlateCarree())
    # genero colorbar para pronos
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
    plt.savefig(salida, dpi=600, bbox_inches='tight')  # , papertype='A4')  # papertype ya no es un param válido
    plt.close()
    cfg.set_correct_group_to_file(salida)  # Change group of file
    saved_message = f"Saved figure: {os.path.basename(salida)}"
    print(saved_message) if not cfg.get('use_logger') else cfg.logger.info(saved_message)
    return


def plot_pronosticos_sissa(pronos, dx, dy, lats, latn, lonw, lone, cmap, colores,
                     titulo, salida):
    """Plot probabilistic forecast"""
    limits = [lonw, lone, lats, -10]
    fig = plt.figure()
    mapproj = ccrs.PlateCarree(central_longitude=(lonw + lone) / 2)
    ax = plt.axes(projection=mapproj)
    ax.set_extent(limits, crs=ccrs.PlateCarree())
    ax.coastlines(alpha=0.5, resolution='50m')
    ax.add_feature(cartopy.feature.BORDERS, linestyle='-', alpha=0.5)
    CS1 = ax.pcolor(dx, dy, pronos, cmap=cmap, transform=ccrs.PlateCarree())
    # genero colorbar para pronos
    plt.title(titulo)
    ax1 = fig.add_axes([0.35, 0.05, 0.3, 0.03])
    cb1 = mpl.colorbar.ColorbarBase(ax1, cmap=cmap, norm=colores, orientation='horizontal')
    plt.savefig(salida, dpi=600, bbox_inches='tight')  # , papertype='A4')  # papertype ya no es un param válido
    plt.close()
    return
