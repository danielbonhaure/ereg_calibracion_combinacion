#!/usr/bin/env python

# OBS:
# El resultado de la calibración sin cross-validation se usa para la combinación en tiempo real "real_time_combination.py"
# El resultado de la calibración con cross-validation se usa para la combinación general "combination.py"

import os
import argparse  # parse command line options
import time  # test time consummed
import configuration
import itertools
import datetime

from calibration import main as calibration
from calibration_sissa import main as calibration_sissa
from get_mme_parameters import main as get_mme_parameters
from real_time_combination import main as real_time_combination
from real_time_combination_sissa import main as real_time_combination_sissa
from plot_rt_forecast import main as plot_rt_forecast
from plot_sissa_forecast import main as plot_sissa_forecast
from create_output_files_descriptor import main as create_descriptors
from script import ScriptControl


cfg = configuration.Config.Instance()


def parse_args() -> argparse.Namespace:

    now = datetime.datetime.now()

    parser = argparse.ArgumentParser(description='Run operational forecast')

    groupm = parser.add_mutually_exclusive_group()
    groupm.add_argument('--models', nargs='+', dest='models',
        default=[], choices=[item[0] for item in cfg.get('models')[1:]], 
        help='Indicates which models should be considered (only used for calibration purposes).')
    groupm.add_argument('--no-models', nargs='+', dest='no_models', 
        default=[], choices=[item[0] for item in cfg.get('models')[1:]], 
        help='Indicates which models should be excluded (only used for calibration purposes).')

    parser.add_argument('--year', type=int, default=now.year,
        help='Indicates the year that should be considered in the forecast generation process.')
    parser.add_argument('--month', type=int, default=now.month,
        help='Indicates the month that should be considered in the forecast generation process.')
    parser.add_argument('--variables', nargs='+', 
        default=["tref", "prec"], choices=["tref", "prec"],
        help='Variables that will be considered in the forecast generation process.')
    parser.add_argument('--weighting', nargs='+', 
        default=["same", "pdf_int", "mean_cor"], choices=["same", "pdf_int", "mean_cor"],
        help='Weighting methods used when combining models.')
    parser.add_argument('--combination', nargs='+', 
        default=["wpdf", "wsereg"], choices=["wpdf", "wsereg"],
        help='Combination methods (count will be ignored when calibration is set as operational).')
    parser.add_argument('--overwrite', action='store_true', 
        help='Indicates if previous generated files should be overwrite or not.')

    parser.add_argument('--calibrate', action='store_true', dest='calibrate',
        help='Indicates if the calibration steps (both, the main and the SISSA specific) should be performed or not.')
    groupc = parser.add_mutually_exclusive_group()
    groupc.add_argument('--ignore-main-calibration', action='store_true', dest='ignore_main_calibration',
        help='Indicates if the main calibration step should be ignored or not.')
    groupc.add_argument('--ignore-sissa-calibration', action='store_true', dest='ignore_sissa_calibration',
        help='Indicates if the SISSA specific calibration step should be ignored or not.')

    parser.add_argument('--ignore-mme-param-gen', action='store_false', dest='mme_param_gen', 
        help='Indicates if the mme parameters generation step should be ignored or not.')

    parser.add_argument('--ignore-combination', action='store_false', dest='combine', 
        help='Indicates if the combination step should be ignored or not.')
    parser.add_argument('--ignore-main-combination', action='store_false', dest='combine_main', 
        help='Indicates if the combination step should be ignored or not.')
    parser.add_argument('--ignore-sissa-combination', action='store_false', dest='combine_sissa',
        help='Indicates if the SISSA specific combination step should be ignored or not.')

    parser.add_argument('--ignore-plotting', action='store_false', dest='plot', 
        help='Indicates if the plotting step should be ignored or not.')
    parser.add_argument('--ignore-main-plotting', action='store_false', dest='plot_main', 
        help='Indicates if the plotting step should be ignored or not.')
    parser.add_argument('--ignore-sissa-plotting', action='store_false', dest='plot_sissa',
        help='Indicates if the SISSA specific plotting step should be ignored or not.')

    parser.add_argument('--cross-validation', action='store_true', dest='cross_validate', 
        help='Indicates if the cross-validation should be done or not (by default, cross-validation is not done).')

    return parser.parse_args()


def main(args):

    if args.calibrate or (not args.ignore_main_calibration and args.ignore_sissa_calibration):
        cfg.logger.info("Starting calibration")
        for v in args.variables:  # loop sobre las variables a calibrar
            for l in range(1, 7+1):  # loop over leadtime --> Forecast leadtime (in months, from 1 to 7)
                for m in range(1, 12+1) if not args.month else [args.month]:  # loop over IC --> Month of initial conditions (from 1 for Jan to 12 for Dec)
                    calibration(argparse.Namespace(variable=[v], IC=[m], leadtime=[l], CV=args.cross_validate,
                                                   OW=args.overwrite, no_models=args.no_models, models=args.models))

    if args.calibrate or (args.ignore_main_calibration and not args.ignore_sissa_calibration):
        cfg.logger.info("Starting calibration SISSA")
        for v in args.variables:  # loop sobre las variables a calibrar
            for m in range(1, 12+1) if not args.month else [args.month]:  # loop over IC --> Month of initial conditions (from 1 for Jan to 12 for Dec)
                for l in range(1, 7+1):  # loop over leadtime --> Forecast leadtime (in months, from 1 to 7)
                    calibration_sissa(argparse.Namespace(variable=[v], IC=[m], leadtime=[l], CV=args.cross_validate,
                                                         OW=args.overwrite))

    if args.mme_param_gen:
        cfg.logger.info("Starting mme parameters generation")
        for v in args.variables:  # loop sobre las variables a calibrar
            for l in range(1, 7+1):  # loop over leadtime --> Forecast leadtime (in months, from 1 to 7)
                for w in args.weighting: 
                    get_mme_parameters(argparse.Namespace(variable=[v], IC=[args.month], leadtime=[l], OW=args.overwrite,
                                                          no_models=args.no_models, models=args.models, wtech=[w]))

    if args.combine and args.combine_main:
        cfg.logger.info("Starting combination")
        for v in args.variables:  # loop sobre las variables a calibrar
            for l in range(1, 7+1):  # loop over leadtime --> Forecast leadtime (in months, from 1 to 7)
                for c, w in itertools.product(args.combination, args.weighting): 
                    real_time_combination(argparse.Namespace(variable=[v], IC=[f"{args.year}-{args.month}-01"], 
                                                             leadtime=[l], no_models=args.no_models, models=args.models,
                                                             ctech=c, wtech=[w]))
    if args.combine and args.combine_sissa:
        cfg.logger.info("Starting combination SISSA")
        for v in args.variables:  # loop sobre las variables a calibrar
            for l in range(1, 7+1):  # loop over leadtime --> Forecast leadtime (in months, from 1 to 7)
                for c, w in itertools.product(args.combination, args.weighting):
                    real_time_combination_sissa(argparse.Namespace(variable=[v], IC=[f"{args.year}-{args.month}-01"],
                                                                   leadtime=[l], no_models=args.no_models, models=args.models, 
                                                                   ctech=c, wtech=[w]))
  
    if args.plot and args.plot_main:
        cfg.logger.info("Starting plotting")
        for v in args.variables:  # loop sobre las variables a calibrar
            for l in range(1, 7+1):  # loop over leadtime --> Forecast leadtime (in months, from 1 to 7)
                plot_rt_forecast(argparse.Namespace(variable=[v], IC=[f"{args.year}-{args.month}-01"], leadtime=[l],
                                                    weighting=args.weighting, combination=args.combination))
    if args.plot and args.plot_sissa:
        cfg.logger.info("Starting plotting SISSA")
        for v in args.variables:  # loop sobre las variables a calibrar
            for l in range(1, 7+1):  # loop over leadtime --> Forecast leadtime (in months, from 1 to 7)
                plot_sissa_forecast(argparse.Namespace(variable=[v], IC=[f"{args.year}-{args.month}-01"], leadtime=[l],
                                                       weighting=args.weighting, combination=args.combination))

    if cfg.get('gen_descriptor', False):
        cfg.logger.info("Starting output files descriptor creation")
        create_descriptors(
            argparse.Namespace(desc_file_type='realtime_forecasts', variables=args.variables,
                               ic_dates=[f"{args.year}-{args.month}-01"], leadtimes=range(1, 7+1),
                               weighting=args.weighting, combination=args.combination))
                

# ==================================================================================================
if __name__ == "__main__":

    # Catch and parse command-line arguments
    parsed_args: argparse.Namespace = parse_args()

    # Check for others scripts
    script_download = ScriptControl('ereg-download')
    script_download.assert_not_running()
    script_hindcast = ScriptControl('ereg-run-hindcast-fcst')
    script_hindcast.assert_not_running()

    try:
        # Get current time
        start = time.time()

        # Create script control
        script = ScriptControl('ereg-run-operational-fcst')

        # Start script execution
        script.start_script()

        # Execute main function
        main(parsed_args)

    except Exception as e:
        error_detected = True  # Set error_detected flag
        raise  # see: http://www.markbetz.net/2014/04/30/re-raising-exceptions-in-python/

    except SystemExit:
        error_detected = False  # when script raise SystemExit

    else:
        error_detected = False  # Set error_detected flag
        script.end_script_execution()

    finally:
        end = time.time()
        err_pfx = "with" if error_detected else "without"
        message = f"Total time to run \"run_operational_forecast.py\" ({err_pfx} errors): {end - start}" 
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
