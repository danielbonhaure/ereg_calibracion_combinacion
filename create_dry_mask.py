"""
Create dry mask where mean seasonal precipitation is less than 1mm/day"""
import warnings
import xarray as xr
import multiprocessing as mp
from pathlib import Path
import configuration

cfg = configuration.Config.Instance()

CORES = mp.cpu_count()
hind_length = 30

warnings.filterwarnings("ignore", category=RuntimeWarning)

coords = cfg.get('coords')
lats = float(coords['lat_s'])
latn = float(coords['lat_n'])
lonw = float(coords['lon_w'])
lone = float(coords['lon_e'])


PATH = cfg.get('folders').get('download_folder')
ruta = Path(PATH, cfg.get('folders').get('nmme').get('root'))
archivo = Path(ruta, 'prec_monthly_nmme_cpc.nc')
dataset = xr.open_dataset(archivo)

dataset = dataset.sel(**{'Y': slice(lats, latn), 'X': slice(lonw, lone)})
dataset['T'] = dataset['T'].astype('datetime64[ns]')
dataset = dataset.sel(T=slice('1991-01-01', '2020-12-31'))

# compute 3-month running mean
ds3m = dataset.rolling(T=3, center=True).sum().dropna('T')
# compute climatological mean
ds3m = ds3m.groupby('T.month').mean(skipna=True)

# create dry mask: seasonal precipitation less than 30mm/month
variable = 'prec'
ds3m[variable] = ds3m[variable] < 90

# save dry mask
PATH = cfg.get('folders').get('gen_data_folder')
ruta = Path(PATH, cfg.get('folders').get('data').get('root'))
ds3m.to_netcdf(Path(ruta, 'dry_mask.nc'))

