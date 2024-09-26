#!/usr/bin/env python

import argparse
import glob
import os
import os.path
import pandas as pd
import time

import configuration


cfg = configuration.Config.Instance()


def parse_args() -> argparse.Namespace:

  parser = argparse.ArgumentParser(description='Remove unused hindcast files')

  parser.add_argument('--remove', action='store_true', dest='remove',
    help='Indicates if unused hindcast files must be removed or not')

  return parser.parse_args()


def generate_filename(variable, year, month, member, model_config_data):
  """ Doc """
  model_name = model_config_data.model
  model_inst = model_config_data.institution
  m_str = str(month).zfill(2)
  forecast_month = month - 1 if month > 1 else 12 
  forecast_year = year if forecast_month == 12 else year + 1
  fm_str = str(forecast_month).zfill(2)
  return f"{variable}_Amon_{model_inst}-{model_name}_{year}{m_str}_r{member}_{year}{m_str}-{forecast_year}{fm_str}.nc"


def generate_hindcast_files(df_modelos):
  """ Doc """
  for model_data in df_modelos.itertuples():
    for variable in ["tref", "prec"]:
      for member in range(1, model_data.members+1, 1):
        for year in range(model_data.hindcast_begin, model_data.hindcast_end+1, 1):
          for month in range(1, 12+1, 1):
            FOLDER = os.path.join(cfg.get('folders').get('download_folder'),
                                  cfg.get('folders').get('nmme').get('hindcast'))
            FILENAME = generate_filename(variable, year, month, member, model_data)
            yield os.path.join(FOLDER, FILENAME)


# ==================================================================================================
if __name__ == "__main__":

  # Catch and parse command-line arguments
  args: argparse.Namespace = parse_args()

  # IDENTIFICAR MODELOS A SER UTILIZADOS
  models_data = cfg.get('models')
  models_urls = cfg.get('models_url')
  df_modelos = pd.merge(
    left=pd.DataFrame(models_data[1:], columns=models_data[0]),
    right=pd.DataFrame(models_urls[1:], columns=models_urls[0]),
    how="inner", on="model"
  )

  # GENERAR ARCHIVOS A SER UTILIZADOS AL CALIBRAR MODELOS
  start = time.time()
  #
  needed_files = list(generate_hindcast_files(df_modelos))
  needed_files.sort()
  #
  end = time.time()
  cfg.logger.info(f'Time to gen hindcast files: {round(end - start, 2)}')

  # LISTAR ARCHIVOS EXISTENTES
  #
  start = time.time()
  #
  FOLDER = os.path.join(cfg.get('folders').get('download_folder'),
                        cfg.get('folders').get('nmme').get('hindcast'))
  existing_files = glob.glob(f'{FOLDER}/*.nc')
  existing_files.sort()
  #
  end = time.time()
  cfg.logger.info(f'Time to get existing files: {round(end - start, 2)}')

  # LISTAR ARCHIVOS EXISTENTES Y ADEMÁS NECESARIOS
  #
  start = time.time()
  #
  common_files = list(set(needed_files) & set(existing_files))
  common_files.sort()
  #
  end = time.time()
  cfg.logger.info(f'Time to get common files: {round(end - start, 2)}')

  # LISTAR ARCHIVOS A SER REMOVIDOS
  #
  start = time.time()
  #
  files_to_be_removed = list(set(existing_files) - set(needed_files))
  files_to_be_removed.sort()
  #
  end = time.time()
  cfg.logger.info(f'Time to identify files to be removed: {round(end - start, 2)}')

  # IMPRIMIR PEQUEÑO REPORTE
  cfg.logger.info(f'needed_files: {len(needed_files)} --- {needed_files[:1]}')
  cfg.logger.info(f'existing_files: {len(existing_files)} --- {existing_files[:1]}')
  cfg.logger.info(f'common_files: {len(common_files)} --- {common_files[:1]}')
  cfg.logger.info(f'files_to_be_removed: {len(files_to_be_removed)} --- {files_to_be_removed[:1]}')

  # BORRAR ARCHIVOS NO NECESARIOS
  if args.remove:
    cfg.logger.info("Running files remove process ... ")
    start = time.time()
    for f in files_to_be_removed:
      cfg.logger.info(f'rm: {f}')
      os.remove(f)
    end = time.time()
    cfg.logger.info(f'Time to remove unused files: {round(end - start, 2)}')
