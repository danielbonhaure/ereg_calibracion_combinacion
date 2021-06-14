"""This module computes calibrates models using ensemble regression"""
import warnings
import numpy as np
import xarray as xr
from scipy.stats import norm
import multiprocessing as mp
from pathos.multiprocessing import ProcessingPool as Pool
from pathlib import Path
import ereg as ensemble_regression
import configuration

CORES = mp.cpu_count()
cfg = configuration.Config.Instance()
PATH = cfg.get("folders").get("download_folder")

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

class Model(object):
    """Model definition"""
    def __init__(self, name, institution, var_name, lat_name,
                 lon_name, miembros_ensamble, leadtimes, hind_begin, hind_end,
                 extension, rt_ensamble):
        #caracteristicas comunes de todos los modelos
        self.name = name
        self.institution = institution
        self.ensembles = miembros_ensamble
        self.leadtimes = leadtimes
        self.var_name = var_name
        self.lat_name = lat_name
        self.lon_name = lon_name
        self.hind_begin = hind_begin
        self.hind_end = hind_end
        self.ext = extension
        self.rt_ensembles = rt_ensamble
    #imprimir caracteristicas generales del modelo
    def __str__(self):
        return "%s is a model from %s and has %s ensemble members and %s leadtimes" % (self.name,
                self.institution, self.ensembles, self.leadtimes)
#comienzo la definición de los métodos

    def select_months(self, init_cond, target, lats, latn, lonw, lone):
        """select forecasted season based on IC and target"""
        #init_cond en meses y target en meses ()
        final_month = init_cond + 11
        if final_month > 12:
            flag_end = 1
            final_month = final_month - 12
        else:
            flag_end = 0
        ruta = Path(PATH, cfg.get('folders').get('nmme').get('hindcast'))
        #abro un archivo de ejemplo
        hindcast_length = self.hind_end - self.hind_begin + 1
        forecast = np.empty([hindcast_length, self.ensembles, int(np.abs(latn - lats)) + 1,
            int(np.abs(lonw - lone)) + 1])
        #loop sobre los anios del hindcast period
        for i in np.arange(self.hind_begin, self.hind_end+1):
            for j in np.arange(1, self.ensembles + 1):
                file = ruta + self.var_name + '_Amon_' + self.institution + '-' +\
                        self.name + '_' + str(i)\
                        + '{:02d}'.format(init_cond) + '_r' + str(j) + '_' + str(i) +\
                        '{:02d}'.format(init_cond) + '-' + str(i + flag_end) + '{:02d}'.format(
                            final_month) + '.' + self.ext

                [variable, latitudes, longitudes] = manipular_nc(file, self.var_name,
                                                                 self.lat_name, self.lon_name,
                                                                 lats, latn, lonw, lone)

                with warnings.catch_warnings():
                    warnings.filterwarnings('error')
                    try:
                        forecast[i - self.hind_begin, j - 1, :, :] = np.nanmean(
                            np.squeeze(np.array(variable))[target:target + 3, :, :], axis=0)
                        #como todos tiene en el 0 el prono del propio
                    except RuntimeWarning:
                        forecast[i - self.hind_begin, j - 1, :, :] = np.NaN
                variable = []
	# Return values of interest: latitudes longitudes forecast
        return latitudes, longitudes, forecast

    def remove_trend(self, forecast, CV_opt):
        """ remove linear trend
        forecast 4-D array ntimes nensembles nlats nlons
        CV_opt boolean"""
        message = "Detrending data"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        [ntimes, nmembers, nlats, nlons] = forecast.shape
        anios = np.arange(ntimes)
        i = np.repeat(np.arange(ntimes, dtype=int), nmembers * nlats * nlons)
        l = np.tile(np.repeat(np.arange(nmembers, dtype=int), nlats * nlons), ntimes)
        j = np.tile(np.repeat(np.arange(nlats, dtype=int), nlons), ntimes * nmembers)
        k = np.tile(np.arange(nlons, dtype=int), ntimes * nmembers * nlats)
        p = Pool(CORES)
        p.clear()

        if CV_opt: #validacion cruzada ventana 1 anio
            message = "Getting cross-validated data"
            print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
            CV_matrix = np.logical_not(np.identity(ntimes))
            def filtro_tendencia(i, l, j, k, anios=anios, CV_m=CV_matrix, forec=forecast):
                y = np.nanmean(forec[:, :, j, k], axis=1) #media del ensamble
                A = np.vstack([anios[CV_m[:, i]], np.ones((anios.shape[0] - 1))])
                m, c = np.linalg.lstsq(A.T, y[CV_m[:, i]], rcond=-1)[0]
                for_dt = forec[i, l, j, k] - (m * anios[i] + c)
                return for_dt
            res = p.map(filtro_tendencia, i.tolist(), l.tolist(), j.tolist(), k.tolist())
            forecast_dt = np.reshape(np.squeeze(np.stack(res)), [ntimes, nmembers, nlats, nlons])
            del(filtro_tendencia, res)
            p.close()
            return forecast_dt

        else:
            message = "Getting hindcast parameters"
            print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
            def filtro_tendencia(i, l, j, k, anios=anios, forec=forecast): #forecast 4D
                y = np.nanmean(forec[:, :, j, k], axis=1)
                A = np.vstack([anios, np.ones(anios.shape[0])])
                m, c = np.linalg.lstsq(A.T, y, rcond=-1)[0]
                for_dt = forec[i, l, j, k] - (m * anios[i] + c)
                return for_dt, m, c
            res = p.map(filtro_tendencia, i.tolist(), l.tolist(), j.tolist(), k.tolist())
            res = np.stack(res, axis=1)
            forecast_dt = np.reshape(res[0, :], [ntimes, nmembers, nlats, nlons])
            a1 = np.reshape(res[1, :], [ntimes, nmembers, nlats, nlons])[0, 0, :, :]
            b1 = np.reshape(res[2, :], [ntimes, nmembers, nlats, nlons])[0, 0, :, :]
            del(filtro_tendencia, res)
            p.close()
            return forecast_dt, a1, b1
    def ereg(self, forecast, observation, CV_opt):
        if CV_opt:
            [forecast_cr, Rm, Rbest, epsbn,
             kmax, K] = ensemble_regression.ensemble_regression(forecast, observation, CV_opt)
            return forecast_cr, Rm, Rbest, epsbn, K
        else:
            [a2, b2, Rm, Rbest, epsbn, kmax, K] = ensemble_regression.ensemble_regression(forecast,
                                                                                      observation,
                                                                                      CV_opt)
            return a2, b2, Rm, Rbest, epsbn, K
    def pdf_eval(self, forecast, eps, observation):
        """obtains pdf intensity at observation point"""
        message = "PDF intensity at observation value"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        [ntimes, nmembers, nlat, nlon] = forecast.shape
        i = np.repeat(np.arange(ntimes, dtype=int), nmembers * nlat * nlon)
        l = np.tile(np.repeat(np.arange(nmembers, dtype=int), nlat * nlon), ntimes)
        j = np.tile(np.repeat(np.arange(nlat, dtype=int), nlon), ntimes * nmembers)
        k = np.tile(np.arange(nlon, dtype=int), ntimes * nmembers * nlat)
        p = Pool(CORES)
        p.clear()

        def evaluo_pdf_normal(i, l, j, k, obs=observation, media=forecast,
                              sigma=eps):
            if np.logical_or(np.logical_or(np.isnan(obs[i, j, k]),
                                           np.isnan(media[i, l, j, k])),
                             np.isnan(sigma[j, k])):
                pdf_intensity = np.NaN
            else:
                with warnings.catch_warnings():
                    warnings.filterwarnings('error')
                    try:
                        pdf_intensity = norm.pdf(obs[i, j, k], loc=media[i, l, j, k],
                                                 scale=np.sqrt(sigma[j, k]))
                    except RuntimeWarning:
                        pdf_intensity = np.NaN

            return pdf_intensity
        res = p.map(evaluo_pdf_normal, i.tolist(), l.tolist(), j.tolist(), k.tolist())
        p.close()
        pdf_intensity = np.reshape(np.squeeze(np.stack(res)), [ntimes, nmembers, nlat, nlon])
        pdf_intensity = np.nanmean(pdf_intensity, axis=1)
        del(p, res, evaluo_pdf_normal)
        #return res
        return pdf_intensity

    def probabilidad_terciles(self, forecast, epsilon, tercil):
        prob_terciles = ensemble_regression.probabilidad_terciles(forecast, epsilon, tercil)
        return prob_terciles

    def computo_terciles(self, forecast, CV_opt):
        message = "Getting model tercile limits"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        #calculo los limites de los terciles para el modelo
        [ntimes, nmembers, nlats, nlons] = forecast.shape
        if CV_opt: #validacion cruzada ventana 1 anio
            i = np.arange(ntimes)
            p = Pool(CORES)
            p.clear()
            CV_matrix = np.logical_not(np.identity(ntimes))

            def cal_terciles(i, CV_m=CV_matrix, forec=forecast):
                A = np.sort(np.rollaxis(np.reshape(forecast[CV_m[:, i], :, :, :],
                                                   [(ntimes - 1) * nmembers, nlats, nlons]),\
                                        0, 3), axis=-1, kind='quicksort')
                lower = A[:, :, np.int(np.round((ntimes - 1) * nmembers / 3) - 1)]
                upper = A[:, :, np.int(np.round((ntimes - 1) * nmembers / 3 * 2) - 1)]
                return lower, upper

            res = p.map(cal_terciles, i.tolist())
            terciles = np.stack(res, axis=1)
            del(cal_terciles, res)
            p.close()

        else:
            A = np.sort(np.rollaxis(np.reshape(forecast, [ntimes * nmembers,
                                                          nlats, nlons]), 0, 3),
                        axis=-1, kind='quicksort')
            upper = A[:, :, np.int(np.round(ntimes * nmembers / 3) - 1)]
            lower = A[:, :, np.int(np.round(ntimes * nmembers /3 * 2) - 1)]
            terciles = np.rollaxis(np.stack([upper, lower], axis=2), 2, 0)
        return terciles

    def computo_categoria(self, forecast, tercil):
        """clasifies each year and ensemble member according to its category"""
        message = "Counting estimate forecast"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        [ntimes, nmembers, nlats, nlons] = forecast.shape
        #calculo el tercil pronosticado
        forecast_terciles = np.empty([3, ntimes, nmembers, nlats, nlons])
        for i in np.arange(ntimes):
            #above normal
            forecast_terciles[0, i, :, :, :] = forecast[i, :, :, :] <= tercil[0, i, :, :]
            #below normal
            forecast_terciles[2, i, :, :, :] = forecast[i, :, :, :] >= tercil[1, i, :, :]
        #near normal
        forecast_terciles[1, :, :, :, :] = np.logical_not(
            np.logical_or(forecast_terciles[0, :, :, :, :], forecast_terciles[2, :, :, :, :]))
        return forecast_terciles

    def select_real_time_months(self,init_month, init_year, target, lats, latn,
                                lonw, lone):
        """select real time forecast season based on IC and target"""
        #init_cond en meses y target en meses ()
        final_month = init_month + 11
        if final_month > 12:
            flag_end = 1
            final_month = final_month - 12
        else:
            flag_end = 0
        ruta = Path(PATH, cfg.get('folders').get('nmme').get('real_time'))
        #abro un archivo de ejemplo
        forecast = np.empty([self.rt_ensembles, int(np.abs(latn - lats)) + 1,
                             int(np.abs(lonw - lone)) + 1])
        if ((init_year == 2011) & (init_month <=11)) & (self.var_name == 'prec')  &\
           (self.name == 'CFSv2'):
            for j in np.arange(1, self.ensembles + 1):
                file = ruta + self.var_name + '_Amon_' + self.institution + '-' +\
                        self.name + '_' + str(init_year) + '{:02d}'.format(init_month) +\
                        '_r' + str(j) + '_' + str(init_year) +\
                        '{:02d}'.format(init_month) + '-' + str(init_year +\
                                                                flag_end) +\
                        '{:02d}'.format(final_month) + '.' + self.ext
                [variable, latitudes, longitudes] = manipular_nc(file, self.var_name,
                                                                 self.lat_name, self.lon_name,
                                                                 lats, latn, lonw, lone)
                forecast[j - 1, :, :] = np.nanmean(np.squeeze(variable)[init_month - 4,
                                                                        target:target + 3,
                                                                        : , :], axis=0)

        elif (init_year == 2011) & (init_month<8) & (((self.var_name == 'tref') &\
                                                   ((self.name != 'CCSM3') &
                                                    (self.name != 'CM2p1') &\
                                        (self.name != 'GMAO'))) |\
           ((self.var_name == 'prec') & ((self.name != 'CCSM3') &  (self.name != 'GMAO')))):
            for j in np.arange(1, self.ensembles + 1):
                file = ruta + self.var_name + '_Amon_' + self.institution + '-' +\
                        self.name + '_' + str(init_year) + '{:02d}'.format(init_month) +\
                        '_r' + str(j) + '_' + str(init_year) +\
                        '{:02d}'.format(init_month) + '-' + str(init_year +\
                                                                flag_end) +\
                        '{:02d}'.format(final_month) + '.' + self.ext
                [variable, latitudes, longitudes] = manipular_nc(file, self.var_name,
                                                                 self.lat_name, self.lon_name,
                                                                 lats, latn, lonw, lone)
                forecast[j - 1, :, :] = np.nanmean(np.squeeze(variable)[init_month - 1,
                                                                        target:target + 3,
                                                                        : , :], axis=0)
        elif (init_year == 2011) & (init_month>=8) & (init_month <=9) & (self.name != 'GMAO'):
            for j in np.arange(1, self.ensembles + 1):
                file = ruta + self.var_name + '_Amon_' + self.institution + '-' +\
                        self.name + '_' + str(init_year) + '{:02d}'.format(init_month) +\
                        '_r' + str(j) + '_' + str(init_year) +\
                        '{:02d}'.format(init_month) + '-' + str(init_year +\
                                                                flag_end) +\
                        '{:02d}'.format(final_month) + '.' + self.ext
                [variable, latitudes, longitudes] = manipular_nc(file, self.var_name,
                                                                 self.lat_name,
                                                                 self.lon_name, lats,
                                                                 latn, lonw, lone)
                forecast[j - 1, :, :] = np.nanmean(np.squeeze(variable)[init_month - 1,
                                                                        target:target + 3,
                                                                        : , :], axis=0)
        elif (init_year == 2011) & (init_month>9) & (init_month <= 11) &\
                ((self.var_name == 'prec') & (self.name != 'GMAO')):
        #((self.name == 'CCSM3') | (self.name == 'FLOR-B01') |\
        #                                      (self.name == 'CanCM4') | (self.name == 'CM2p1'))):
            for j in np.arange(1, self.ensembles + 1):
                file = ruta + self.var_name + '_Amon_' + self.institution + '-' +\
                        self.name + '_' + str(init_year) + '{:02d}'.format(init_month) +\
                        '_r' + str(j) + '_' + str(init_year) +\
                        '{:02d}'.format(init_month) + '-' + str(init_year +\
                                                                flag_end) +\
                        '{:02d}'.format(final_month) + '.' + self.ext
                [variable, latitudes, longitudes] = manipular_nc(file, self.var_name,
                                                                 self.lat_name,
                                                                 self.lon_name, lats,
                                                                 latn, lonw, lone)
                forecast[j - 1, :, :] = np.nanmean(np.squeeze(variable)[init_month - 1,
                                                                        target:target + 3,
                                                                        : , :], axis=0)
        else:
            for j in np.arange(1, self.ensembles + 1):
                file = ruta + self.var_name + '_Amon_' + self.institution + '-' + self.name + '_'\
                        + str(init_year) + '{:02d}'.format(init_month) + '_r' +\
                        str(j) + '_' + str(init_year) +\
                        '{:02d}'.format(init_month) + '-' + str(init_year +\
                                                                flag_end) +\
                        '{:02d}'.format(final_month) + '.' + self.ext
                [variable, latitudes, longitudes] = manipular_nc(file, self.var_name,
                                                                 self.lat_name, self.lon_name,
                                                                 lats, latn, lonw, lone)
                with warnings.catch_warnings():
                    warnings.filterwarnings('error')
                    try:
                        forecast[j - 1, :, :] = np.nanmean(np.squeeze(
                        np.array(variable))[target:target + 3, :, :], axis=0)
                        #como todos tiene en el 0 el prono del propio
                    except RuntimeWarning:
                        forecast[j - 1, :, :] = np.NaN
                variable = []
        return latitudes, longitudes, forecast

