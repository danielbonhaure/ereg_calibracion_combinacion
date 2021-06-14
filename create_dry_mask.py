"""
Create dry mask where mean seasonal precipitation is less than 1mm/day"""
import datetime
import warnings
import numpy as np
import xarray as xr
import multiprocessing as mp
from pathos.multiprocessing import ProcessingPool as Pool
from pandas.tseries.offsets import *
from pathlib import Path
import configuration

cfg = configuration.Config.Instance()

CORES = mp.cpu_count()
PATH = cfg.get('folders').get("download_folder")
ruta = Path(PATH, cfg.get('folders').get('nmme').get('root'))
hind_length = 28

warnings.filterwarnings("ignore", category=RuntimeWarning)

archivo = Path(ruta, 'prec_monthly_nmme_cpc.nc')
coords = cfg.get('coords')
lats = float(coords['lat_s'])
latn = float(coords['lat_n'])
lonw = float(coords['lon_w'])
lone = float(coords['lon_e'])
variable = 'prec'

#hay problemas para decodificar las fechas, genero un xarray con mis fechas decodificadas
dataset = xr.open_dataset(archivo, decode_times=False)
var_out = dataset[variable].sel(**{'Y': slice(lats, latn), 'X': slice(lonw, lone)})
lon = dataset['X'].sel(**{'X': slice(lonw, lone)})
lat = dataset['Y'].sel(**{'Y': slice(lats, latn)})
numero = [int(s) for s in dataset.T.units.split() if s.isdigit()]

pivot = datetime.datetime(1960, 1, 1) #dificilmente pueda obtener este atributo del nc sin
#poder decodificarlo con xarray
time = [pivot + DateOffset(months=int(x), days=15) for x in dataset['T']]
#genero xarray con estos datos para obtener media estacional
ds = xr.Dataset({variable: (('time', 'Y', 'X'), var_out)},
                coords={'time': time, 'Y': lat, 'X': lon})
#compute 3-month running mean
ds3m = ds.rolling(time=3, center=True).mean(dim='time')
#compute climatological mean
ds3m = ds3m.groupby('time.month').mean(skipna=True)
#create dry mask: seasonal precipitation less than 30mm/month
ds3m[variable] = ds['prec'] <=30

ds3m.to_netcdf(Path(PATH, cfg.get('folders').get('data').get('root'), 'dry_mask.nc'))
