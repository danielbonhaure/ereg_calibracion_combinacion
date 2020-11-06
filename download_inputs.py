#!/usr/bin/env python

import argparse #parse command line options
import calendar
import helpers
import configuration
import pandas as pd
import urllib.request
import urllib.parse
import xarray as xr
import os
import os.path
import datetime
import time
import yaml
import logging
import sys
import cdo
import netCDF4


cfg = configuration.Config.Instance()

RUTA_IRI = "http://iridl.ldeo.columbia.edu/SOURCES/.Models/.NMME/"

with helpers.localized("en_US.utf8"):
  MONTHS_ABBR = list(calendar.month_abbr)


def generate_download_url(variable, forecast_start_year, forecast_start_month_abbr, member_or_realization, model_config_data, data_type):
  model_specific_url = (f"{model_config_data.url_model_part}/" + 
      (f"{model_config_data.url_hindcast_part}" if data_type == 'hindcast' else f"{model_config_data.url_forecast_part}")) 
  # Forecast Start Time (forecast_reference_time)
  #   grid: /S (months since 1960-01-01) ordered (0000 1 Feb 1981) to (0000 1 Jan 2017) by 1.0 N= 432 pts :grid
  forecast_start_time = f"(0000 1 {forecast_start_month_abbr} {forecast_start_year} )"
  # Ensemble Member (realization)
  #   grid: /M (unitless) ordered (1.0) to (x.0) by 1.0 N= x pts :grid
  ensemble_member = f"({member_or_realization}.0 )"
  return f"{RUTA_IRI}{model_specific_url}/.{variable}/S/{forecast_start_time}VALUES/M/{ensemble_member}VALUES/data.nc"


def generate_filename(variable, year, month, member, model_config_data, data_type):
  #
  model_name = model_config_data.model
  model_inst = model_config_data.institution
  m_str = str(month).zfill(2)
  forecast_month = month - 1 if month > 1 else 12 
  forecast_year = year if forecast_month == 12 else year + 1
  fm_str = str(forecast_month).zfill(2)
  return f"{variable}_Amon_{model_inst}-{model_name}_{year}{m_str}_r{member}_{year}{m_str}-{forecast_year}{fm_str}.nc"


def check_file(filename, recheck=False):
  #
  if not os.path.isfile(filename):
    return False
  if recheck:
    # Check file size
    if os.stat(filename).st_size == 0:
      return False
    # Check if file can be opened
    if filename.endswith('.nc'):
      try:
        d = xr.open_dataset(filename, decode_times=False)
        d.close()
      except Exception as e:
        return False
  return True


def links_to_download_hindcast(df_modelos, recheck, redownload):
  # 
  for model_data in df_modelos.itertuples():
    for variable in ["tref", "prec"]:
      for member in range(1, model_data.members+1, 1): 
        for year in range(model_data.hindcast_begin, model_data.hindcast_end+1, 1):
          for month, month_abbr in zip(range(1,13), MONTHS_ABBR[1:]):
            FOLDER = f"{cfg.get('download_folder')}/NMME/hindcast/".replace("//","/")
            DOWNLOAD_URL = generate_download_url(variable, year, month_abbr, member, model_data, "hindcast")
            FILENAME = generate_filename(variable, year, month, member, model_data, "hindcast")
            DOWNLOAD_STATUS = check_file(FOLDER+FILENAME, recheck) if not redownload else False
            yield {'FILENAME': FOLDER+FILENAME, 'DOWNLOAD_URL': DOWNLOAD_URL, 
                   'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'hindcast'}


def links_to_download_operational(df_modelos, year, recheck, redownload):
  # 
  now = datetime.datetime.now()
  for model_data in df_modelos.itertuples():
    for variable in ["tref", "prec"]:
      for member in range(1, model_data.members+1, 1): 
        for month, month_abbr in zip(range(1, now.month+1 if year == now.year else 13), MONTHS_ABBR[1:]):
          FOLDER = f"{cfg.get('download_folder')}/NMME/real_time/".replace("//","/")
          DOWNLOAD_URL = generate_download_url(variable, year, month_abbr, member, model_data, "operational")
          FILENAME = generate_filename(variable, year, month, member, model_data, "operational")
          DOWNLOAD_STATUS = check_file(FOLDER+FILENAME, recheck) if not redownload else False
          yield {'FILENAME': FOLDER+FILENAME, 'DOWNLOAD_URL': DOWNLOAD_URL, 
                 'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'operational'}


def links_to_download_real_time(df_modelos, year, month, recheck, redownload):
  # 
  month_abbr = MONTHS_ABBR[month]
  for model_data in df_modelos.itertuples():
    for variable in ["tref", "prec"]:
      for member in range(1, model_data.members+1, 1): 
        FOLDER = f"{cfg.get('download_folder')}/NMME/real_time/".replace("//","/")
        DOWNLOAD_URL = generate_download_url(variable, year, month_abbr, member, model_data, "real_time")
        FILENAME = generate_filename(variable, year, month, member, model_data, "real_time")
        DOWNLOAD_STATUS = check_file(FOLDER+FILENAME, recheck) if not redownload else False
        yield {'FILENAME': FOLDER+FILENAME, 'DOWNLOAD_URL': DOWNLOAD_URL, 
               'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'real_time'}


def links_to_download_observation(recheck, redownload):
  #
  FOLDER = f"{cfg.get('download_folder')}/NMME/hindcast/".replace("//","/")
  #
  FILENAME = "prec_monthly_nmme_cpc.nc"
  DOWNLOAD_URL = f"{RUTA_IRI}.CPC-CMAP-URD/.prate/data.nc"
  DOWNLOAD_STATUS = check_file(FOLDER+FILENAME, recheck) if not redownload else False
  yield {'FILENAME': FOLDER+FILENAME, 'DOWNLOAD_URL': DOWNLOAD_URL, 
         'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'observation'}
  #
  FILENAME = "tref_monthly_nmme_ghcn_cams.nc"
  DOWNLOAD_URL = f"{RUTA_IRI}.GHCN_CAMS/.updated/data.nc"
  DOWNLOAD_STATUS = check_file(FOLDER+FILENAME, recheck) if not redownload else False
  yield {'FILENAME': FOLDER+FILENAME, 'DOWNLOAD_URL': DOWNLOAD_URL, 
         'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'observation'}
  #
  FILENAME = "lsmask.nc"
  DOWNLOAD_URL = f"{RUTA_IRI}.LSMASK/.land/data.nc"
  DOWNLOAD_STATUS = check_file(FOLDER+FILENAME, recheck) if not redownload else False
  yield {'FILENAME': FOLDER+FILENAME, 'DOWNLOAD_URL': DOWNLOAD_URL, 
         'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'observation'}


def modify_downloaded_file_if_needed(downloaded_file):
  #
  tempfile = downloaded_file.replace('.nc', '_TMP.nc')
  #
  filename = 'prec_monthly_nmme_cpc.nc'
  if downloaded_file.endswith(filename) and os.path.isfile(filename):
    with netCDF4.Dataset(downloaded_file, "r+", format="NETCDF4") as nc:
      nc.renameVariable('prate', 'prec')
    cdo.Cdo().selyear('1982/2011', input=downloaded_file, output=tempfile)
    os.replace(tempfile, downloaded_file)
  #
  filename = 'tref_monthly_nmme_ghcn_cams.nc'
  if downloaded_file.endswith(filename) and os.path.isfile(filename):
    with netCDF4.Dataset(downloaded_file, "r+", format="NETCDF4") as nc:
      nc.renameVariable('t2m', 'tref')
    cdo.Cdo().addc("273.15",input=downloaded_file, output=tempfile)
    os.replace(tempfile, downloaded_file)
  #
  if os.path.isfile(tempfile):
    os.remove(tempfile)


def download_file(download_url, filename):
  #
  download_url = urllib.parse.quote(download_url, safe=':/')
  # Download file
  f, h = urllib.request.urlretrieve(download_url, filename)
  # Check file size
  assert os.stat(filename).st_size != 0
  # Check if file can be opened
  if filename.endswith('.nc'):
    d = xr.open_dataset(filename, decode_times=False)
    d.close()
  modify_downloaded_file_if_needed(filename)


# ==================================================================================================
if __name__ == "__main__":
  now = datetime.datetime.now()
  
  # PROCESAR ARGUMENTOS
  parser = argparse.ArgumentParser(description='Download input data')
  parser.add_argument('--download', nargs='+', default=['all'],
    choices=['hindcast','operational','real_time','observation','all'], 
    help='Indicates which input data should be downloaded')
  parser.add_argument('--year', type=int, default=now.year,
    help='Indicates input data of which years should be downloaded for operational and real-time execution')
  parser.add_argument('--month', type=int, default=now.month,
    help='Indicates input data of which months should be downloaded for real-time execution')
  parser.add_argument('--re-check', action='store_true', dest='recheck',
    help='Indicates if previously downloaded files must be checked or not')
  parser.add_argument('--re-download', action='store_true', dest='redownload',
    help='Indicates if previously downloaded files must be downloaded again')
  parser.add_argument('--models', nargs='+', default=[],
    help='Indicates which models should be considered when downloading input files')
  args = parser.parse_args()  # Extract dates from args
  # args = argparse.Namespace(download=['all'], year=2020, month=6, recheck=False, redownload=True)
  
  
  # INFORMAR SOBRE VERIFICACIÓN Y RE-DESCARGA DE ARCHIVOS
  if args.redownload:
    cfg.logger.info(f'Previously downloaded files will be downloaded again!')
  else:
    cfg.logger.info(f'Previously downloaded files will{" " if args.recheck else " not "}be verified!')
    
  
  # IDENTIFICAR MODELOS A SER UTILIZADOS
  models_data = cfg.get('models')
  models_urls = cfg.get('models_url')
  df_modelos = pd.merge(
    left=pd.DataFrame(models_data[1:], columns=models_data[0]),
    right=pd.DataFrame(models_urls[1:], columns=models_urls[0]),
    how="inner", on="model"
  )
  
  # SELECCIONAR SOLO MODELOS INDICADOS EN EL PARÁMETRO "--models"
  if args.models:
    df_modelos = df_modelos.query(f'model in {args.models}')
  
  # GENERAR LINKS DE DESCARGA
  df_links = pd.DataFrame(columns=['FILENAME','DOWNLOAD_URL','DOWNLOADED','TYPE'])
  if any(item in ['hindcast', 'all'] for item in args.download):
    start = time.time()
    links = links_to_download_hindcast(df_modelos, args.recheck, args.redownload)
    df_links = df_links.append(pd.DataFrame.from_dict(links), ignore_index=True)
    end = time.time()
    cfg.logger.info(f'Time to gen{" and recheck " if args.recheck else " "}hindcast links: {round(end - start, 2)}')
  if any(item in ['operational', 'all'] for item in args.download):
    start = time.time()
    links = links_to_download_operational(df_modelos, args.year, args.recheck, args.redownload)
    df_links = df_links.append(pd.DataFrame.from_dict(links), ignore_index=True)
    end = time.time()
    cfg.logger.info(f'Time to gen{" and recheck " if args.recheck else " "}operational links: {round(end - start, 2)} -> anho: {args.year}')
  if any(item in ['real_time', 'all'] for item in args.download):
    start = time.time()
    links = links_to_download_real_time(df_modelos, args.year, args.month, args.recheck, args.redownload)
    df_links = df_links.append(pd.DataFrame.from_dict(links), ignore_index=True)
    end = time.time()
    cfg.logger.info(f'Time to gen{" and recheck " if args.recheck else " "}real_time links: {round(end - start, 2)} -> anho: {args.year}, mes: {args.month}')
  if any(item in ['observation', 'all'] for item in args.download):
    start = time.time()
    links = links_to_download_observation(args.recheck, args.redownload)
    df_links = df_links.append(pd.DataFrame.from_dict(links), ignore_index=True)
    end = time.time()
    cfg.logger.info(f'Time to gen{" and recheck " if args.recheck else " "}observation links: {round(end - start, 2)}')
  
  total_files = df_links['DOWNLOADED'].count()
  n_downloaded_files = df_links['DOWNLOADED'].sum()
  n_files_to_download = total_files - n_downloaded_files
  cfg.logger.info(f"Total files: {total_files}, "+
                  f"Downloaded files: {n_downloaded_files}, "+
                  f"Not yet downloaded files: {n_files_to_download}")
  
  # DESCARGAR ARCHIVOS
  cfg.logger.info("Running files download process ... ")
  count_downloaded_files, count_failed_downloads = 0, 0
  if n_files_to_download:
    run_status = f'Downloading ereg input files (PID: {os.getpid()})'
    helpers.progress_bar(count_downloaded_files, n_files_to_download, status=run_status)
    for row in df_links.query('DOWNLOADED == False').itertuples():
      try:
        download_file(row.DOWNLOAD_URL, row.FILENAME)
      except Exception as e:
        helpers.progress_bar_clear_line()
        cfg.logger.error(e)
        cfg.logger.warning(f'Failed to download file "{row.FILENAME}" from url "{row.DOWNLOAD_URL}"')
        count_failed_downloads += 1
      else:
        df_links.at[row.Index, 'DOWNLOADED'] = True
        count_downloaded_files += 1
      helpers.progress_bar(count_downloaded_files+count_failed_downloads, n_files_to_download, status=run_status)
    helpers.progress_bar_close()
    cfg.logger.info(f"{count_downloaded_files} files were downloaded successfully and "+
                    f"{count_failed_downloads} downloads failed!")
  else:
    cfg.logger.info("There isn't files to download!!")
    
  if cfg.email and count_failed_downloads:
    cfg.logger.info("Sending email with download failures")
    helpers.send_email(
      from_addr = cfg.email.get('address'), 
      password = cfg.email.get('password'), 
      to_addrs = cfg.email.get('to_addrs'), 
      subject = 'Archivos no descargados - EREG SMN', 
      body = df_links.query('DOWNLOADED == False').to_html()             
    )
