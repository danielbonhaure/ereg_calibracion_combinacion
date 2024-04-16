#!/usr/bin/env python

import argparse  # parse command line options
import calendar
import helpers
import configuration
import pandas as pd
import urllib.request
import urllib.parse
import urllib.error
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
import numpy as np
import shutil

cfg = configuration.Config.Instance()

def generate_download_url(variable, forecast_start_year, forecast_start_month, member_or_realization, model_config_data, data_type):
  model_specific_url = (f"{model_config_data.url_model_part}/" + 
      (f"{model_config_data.url_hindcast_part}" if data_type == 'hindcast' else f"{model_config_data.url_forecast_part}")) 
  # Forecast Start Time (forecast_reference_time)
  #   grid: /S (months since 1960-01-01) ordered (0000 1 Feb 1981) to (0000 1 Jan 2017) by 1.0 N= 432 pts :grid
  forecast_start_time = f"(0000 1 {calendar.month_abbr[forecast_start_month]} {forecast_start_year} )"
  # Ensemble Member (realization)
  #   grid: /M (unitless) ordered (1.0) to (x.0) by 1.0 N= x pts :grid
  ensemble_member = f"({member_or_realization}.0 )"
  return f"{cfg.get('iri_url')}{model_specific_url}/.{variable}/S/{forecast_start_time}VALUES/M/{ensemble_member}VALUES/data.nc"


def generate_filename(variable, year, month, member, model_config_data, data_type):
  #
  model_name = model_config_data.model
  model_inst = model_config_data.institution
  m_str = str(month).zfill(2)
  forecast_month = month - 1 if month > 1 else 12 
  forecast_year = year if forecast_month == 12 else year + 1
  fm_str = str(forecast_month).zfill(2)
  return f"{variable}_Amon_{model_inst}-{model_name}_{year}{m_str}_r{member}_{year}{m_str}-{forecast_year}{fm_str}.nc"


def check_file(filename, variable, recheck=False):
  #
  if not os.path.isfile(filename):
    return False
  if recheck:
    # Check file size
    if os.stat(filename).st_size == 0:
      return False
    # Check if file can be opened and contains valid values
    if str(filename).endswith('.nc'):
      try:
        # Check if file can be opened
        d = xr.open_dataset(filename, decode_times=False)
      except Exception as e:
        return False
      else:
        # Check if file contains valid values
        v = d.get(variable)
        if v is None:
          return False
        elif np.isnan(float(v.max(skipna=True))):
          return False
        d.close()
  return True


def links_to_download_hindcast(df_modelos, recheck, redownload):
  # 
  for model_data in df_modelos.itertuples():
    for variable in ["tref", "prec"]:
      for member in range(1, model_data.members+1, 1):
        if recheck:
          cfg.logger.info(f'Checking files: for: model={model_data.model}, variable={variable}, member={member}')
        for year in range(model_data.hindcast_begin, model_data.hindcast_end+1, 1):
          for month in range(1, 12+1, 1):
            FOLDER = os.path.join(cfg.get('folders').get('download_folder'),
                                  cfg.get('folders').get('nmme').get('hindcast'))

            if model_data.model == "GEM5-NEMO":
              DOWNLOAD_URL = generate_download_url(variable, year, month, member + 10, model_data, "hindcast")
            else:
              DOWNLOAD_URL = generate_download_url(variable, year, month, member, model_data, "hindcast")

            FILENAME = generate_filename(variable, year, month, member, model_data, "hindcast")
            DOWNLOAD_STATUS = check_file(os.path.join(FOLDER, FILENAME), variable, recheck) if not redownload else False
            yield {'FILENAME': os.path.join(FOLDER, FILENAME), 'DOWNLOAD_URL': DOWNLOAD_URL,
                   'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'hindcast', 'VARIABLE': variable}


def links_to_download_operational(df_modelos, year, recheck, redownload):
  # 
  now = datetime.datetime.now()
  for model_data in df_modelos.itertuples():
    for variable in ["tref", "prec"]:
      for member in range(1, model_data.members+1, 1): 
        for month in range(1, now.month+1 if year == now.year else 12+1, 1):
          FOLDER = os.path.join(cfg.get('folders').get('download_folder'),
                                cfg.get('folders').get('nmme').get('real_time'))

          if model_data.model == "GEM5-NEMO":
            DOWNLOAD_URL = generate_download_url(variable, year, month, member + 10, model_data, "operational")
          else:
            DOWNLOAD_URL = generate_download_url(variable, year, month, member, model_data, "operational")

          FILENAME = generate_filename(variable, year, month, member, model_data, "operational")
          DOWNLOAD_STATUS = check_file(os.path.join(FOLDER, FILENAME), variable, recheck) if not redownload else False
          yield {'FILENAME': os.path.join(FOLDER, FILENAME), 'DOWNLOAD_URL': DOWNLOAD_URL,
                 'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'operational', 'VARIABLE': variable}


def links_to_download_real_time(df_modelos, year, month, recheck, redownload):
  # 
  for model_data in df_modelos.itertuples():
    for variable in ["tref", "prec"]:
      for member in range(1, model_data.members+1, 1): 
        FOLDER = os.path.join(cfg.get('folders').get('download_folder'),
                              cfg.get('folders').get('nmme').get('real_time'))

        if model_data.model == "GEM5-NEMO":
          DOWNLOAD_URL = generate_download_url(variable, year, month, member + 10, model_data, "real_time")
        else:
          DOWNLOAD_URL = generate_download_url(variable, year, month, member, model_data, "real_time")

        FILENAME = generate_filename(variable, year, month, member, model_data, "real_time")
        DOWNLOAD_STATUS = check_file(os.path.join(FOLDER, FILENAME), variable, recheck) if not redownload else False
        yield {'FILENAME': os.path.join(FOLDER, FILENAME), 'DOWNLOAD_URL': DOWNLOAD_URL,
               'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'real_time', 'VARIABLE': variable}


def links_to_download_observation(recheck, redownload):
  #
  FOLDER = os.path.join(cfg.get('folders').get('download_folder'),
                        cfg.get('folders').get('nmme').get('root'))
  #
  FILENAME = "prec_monthly_nmme_cpc.nc"
  DOWNLOAD_URL = f"{cfg.get('iri_url')}.CPC-CMAP-URD/.prate/data.nc"
  DOWNLOAD_STATUS = check_file(os.path.join(FOLDER, FILENAME), 'prec', recheck) if not redownload else False
  yield {'FILENAME': os.path.join(FOLDER, FILENAME), 'DOWNLOAD_URL': DOWNLOAD_URL,
         'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'observation', 'VARIABLE': 'prec'}
  #
  FILENAME = "tref_monthly_nmme_ghcn_cams.nc"
  DOWNLOAD_URL = f"{cfg.get('iri_url')}.GHCN_CAMS/.updated/data.nc"
  DOWNLOAD_STATUS = check_file(os.path.join(FOLDER, FILENAME), 'tref', recheck) if not redownload else False
  yield {'FILENAME': os.path.join(FOLDER, FILENAME), 'DOWNLOAD_URL': DOWNLOAD_URL,
         'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'observation', 'VARIABLE': 'tref'}
  #
  FILENAME = "lsmask.nc"
  DOWNLOAD_URL = f"{cfg.get('iri_url')}.LSMASK/.land/data.nc"
  DOWNLOAD_STATUS = check_file(os.path.join(FOLDER, FILENAME), 'land', recheck) if not redownload else False
  yield {'FILENAME': os.path.join(FOLDER, FILENAME), 'DOWNLOAD_URL': DOWNLOAD_URL,
         'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'observation', 'VARIABLE': 'land'}


def links_to_download_observation_for_verification(recheck, redownload):
  #
  FOLDER = os.path.join(cfg.get('folders').get('download_folder'),
                        cfg.get('folders').get('nmme').get('root'))
  #
  FILENAME = "precip.mon.mean.nc"
  DOWNLOAD_URL = "https://downloads.psl.noaa.gov/Datasets/cmap/std/precip.mon.mean.nc"
  DOWNLOAD_STATUS = check_file(os.path.join(FOLDER, FILENAME), 'precip', recheck) if not redownload else False
  yield {'FILENAME': os.path.join(FOLDER, FILENAME), 'DOWNLOAD_URL': DOWNLOAD_URL,
         'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'observation', 'VARIABLE': 'precip'}
  #
  FILENAME = "air.mon.mean.nc"
  DOWNLOAD_URL = "https://downloads.psl.noaa.gov/Datasets/ghcncams/air.mon.mean.nc"
  DOWNLOAD_STATUS = check_file(os.path.join(FOLDER, FILENAME), 'air', recheck) if not redownload else False
  yield {'FILENAME': os.path.join(FOLDER, FILENAME), 'DOWNLOAD_URL': DOWNLOAD_URL,
         'DOWNLOADED': DOWNLOAD_STATUS, 'TYPE': 'observation', 'VARIABLE': 'air'}


def modify_downloaded_file_if_needed(downloaded_file):
  #
  tempfile = str(downloaded_file).replace('.nc', '_TMP.nc')
  #
  filename = 'prec_monthly_nmme_cpc.nc'
  if str(downloaded_file).endswith(filename) and os.path.isfile(downloaded_file):
    cfg.logger.info(f'Modifying file {filename}. Renaming variable "prate" to "prec".')
    with netCDF4.Dataset(downloaded_file, "r+", format="NETCDF4") as nc:
      nc.renameVariable('prate', 'prec')
    cfg.logger.info(f'Modifying file {filename}. Selecting years (from 1982 to 2011).')
    cdo.Cdo().selyear('1982/2011', input=downloaded_file, output=tempfile)
    os.replace(tempfile, downloaded_file)
  #
  filename = 'tref_monthly_nmme_ghcn_cams.nc'
  if str(downloaded_file).endswith(filename) and os.path.isfile(downloaded_file):
    cfg.logger.info(f'Modifying file {filename}. Renaming variable "t2m" to "tref".')
    with netCDF4.Dataset(downloaded_file, "r+", format="NETCDF4") as nc:
      nc.renameVariable('t2m', 'tref')
    cfg.logger.info(f'Modifying file {filename}. Adding 273.15 to values in file.')
    cdo.Cdo().addc("273.15", input=downloaded_file, output=tempfile)
    os.replace(tempfile, downloaded_file)
  #
  if os.path.isfile(tempfile):
    os.remove(tempfile)


def download_file(download_url, filename, variable):
  #
  download_url = urllib.parse.quote(download_url, safe=':/')
  # Create progress bar to track downloading
  pb = helpers.DownloadProgressBar(os.path.basename(filename))
  # Add headers to request
  opener = urllib.request.build_opener()
  opener.addheaders = [('User-agent', 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64)')]
  urllib.request.install_opener(opener)
  # Download file
  try:
    tmp_file, h = urllib.request.urlretrieve(url=download_url, reporthook=pb)
  except urllib.error.HTTPError as e:
    cfg.logger.error(f'HTTPError {e.code} "{e.reason}" downloading: {download_url}')
    raise
  except Exception as e:
    cfg.logger.error(f'Error {type(e).__name__} downloading: {download_url}')
    raise
  else:
    shutil.move(tmp_file, filename)
  finally:
    urllib.request.urlcleanup()  # Clean up temporary files
  # Change group of file
  cfg.set_correct_group_to_file(filename)
  # Check file size
  assert os.stat(filename).st_size != 0, \
    f'Size equal 0 for file {filename}'
  # Modify files when needed
  modify_downloaded_file_if_needed(filename)
  # Check if file can be opened and contains valid values
  if str(filename).endswith('.nc'):
    d = xr.open_dataset(filename, decode_times=False)
    assert not np.isnan(float(d.get(variable).max(skipna=True))), \
      f'All NaN values for {variable} in file {filename}'
    d.close()


# ==================================================================================================
if __name__ == "__main__":

  # Set pid file
  pid_file = '/tmp/ereg-download.pid'

  # Get PID and save it to a file
  with open(pid_file, 'w') as f:
    f.write(f'{os.getpid()}')

  # Get start time
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
    choices=[item[0] for item in cfg.get('models')[1:]],
    help='Indicates which models should be considered when downloading input files')
  
  # EXTRACT DATE FROM ARGS
  args = parser.parse_args()
  # Args for testing purposes
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
    df_links = pd.concat([df_links, pd.DataFrame.from_dict(links)], ignore_index=True)
    end = time.time()
    cfg.logger.info(f'Time to gen{" and recheck " if args.recheck else " "}hindcast links: {round(end - start, 2)}')
  if any(item in ['operational', 'all'] for item in args.download):
    start = time.time()
    links = links_to_download_operational(df_modelos, args.year, args.recheck, args.redownload)
    df_links = pd.concat([df_links, pd.DataFrame.from_dict(links)], ignore_index=True)
    obs_links = links_to_download_observation_for_verification(args.recheck, args.redownload)
    df_links = pd.concat([df_links, pd.DataFrame.from_dict(obs_links)], ignore_index=True)
    end = time.time()
    cfg.logger.info(f'Time to gen{" and recheck " if args.recheck else " "}operational links: {round(end - start, 2)} -> year: {args.year}')
  if any(item in ['real_time', 'all'] for item in args.download):
    start = time.time()
    links = links_to_download_real_time(df_modelos, args.year, args.month, args.recheck, args.redownload)
    df_links = pd.concat([df_links, pd.DataFrame.from_dict(links)], ignore_index=True)
    end = time.time()
    cfg.logger.info(f'Time to gen{" and recheck " if args.recheck else " "}real_time links: {round(end - start, 2)} -> year: {args.year}, month: {args.month}')
  if any(item in ['observation', 'all'] for item in args.download):
    start = time.time()
    links = links_to_download_observation(args.recheck, args.redownload)
    df_links = pd.concat([df_links, pd.DataFrame.from_dict(links)], ignore_index=True)
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
    progress_bar = helpers.ProgressBar(n_files_to_download, run_status)
    for row in df_links.query('DOWNLOADED == False').itertuples():
      progress_bar.report_advance(0)
      try:
        download_file(row.DOWNLOAD_URL, row.FILENAME, row.VARIABLE)
      except Exception as e:
        progress_bar.clear_line()
        cfg.logger.error(e)
        cfg.logger.warning(f'Failed to download file "{row.FILENAME}" from url "{row.DOWNLOAD_URL}"')
        count_failed_downloads += 1
      else:
        df_links.at[row.Index, 'DOWNLOADED'] = True
        count_downloaded_files += 1
      progress_bar.report_advance(1)
    progress_bar.close()
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

  # Finally, remove pid file
  os.remove(pid_file)
