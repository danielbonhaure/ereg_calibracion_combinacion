"""functions to combine ensemble forecast using ereg"""
import warnings
import numpy as np
import multiprocessing as mp
import configuration

from scipy.stats import norm
from pathos.multiprocessing import ProcessingPool as Pool
warnings.filterwarnings("ignore", category=RuntimeWarning)
CORES = mp.cpu_count()
cfg = configuration.Config.Instance()

def ensemble_regression(forecast, observation, CV_opt):
    """Calibrates forecast using ensemble regression"""
    message = "Applying Ensemble Regression"
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
    [ntimes, nmembers, nlats, nlons] = forecast.shape
    p = Pool(CORES)
    p.clear()
    if CV_opt: #validacion cruzada ventana 1 anio
        i = np.arange(ntimes, dtype=int)
        CV_matrix = np.logical_not(np.identity(ntimes))
        def compute_clim(i, CV_m=CV_matrix, obs=observation, forec=forecast):
            #computes climatologies under CV
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                obs_c = np.nanmean(obs[CV_m[:, i], :, :], axis=0)
            em_c = np.nanmean(np.nanmean(forec[CV_m[:, i], :, :, :], axis=1),
                           axis=0)
            return obs_c, em_c
        res = p.map(compute_clim, i.tolist())
        res = np.stack(res, axis=1)
        obs_c = res[0, :, :, :]
        em_c = res[1, :, :, :]
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            obs_c = np.nanmean(observation, axis=0)
        em_c = np.nanmean(np.nanmean(forecast, axis=1), axis=0)

    em = np.nanmean(forecast, axis=1)
    signal = np.nanmean(np.power(em - em_c, 2), axis=0)
    noise = np.nanmean(np.nanvar(forecast, axis=1), axis=0) #noise
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        obs_var = np.nansum(np.power(observation - obs_c, 2), axis=0) / ntimes
        Rm = np.nanmean((observation - obs_c) * (em - em_c), axis=0) / np.sqrt(obs_var * signal)
    #Rbest = Rm sqrt( 1 + (m/(m - 1) * N) /S )
    Rbest = Rm * np.sqrt(1 + (nmembers / (nmembers - 1) * noise) / signal)
    #epsbest = n/(n-1) * Varobs * (1-Rmean**2)
    epsbn = (ntimes / (ntimes - 1)) *  obs_var * (1 - np.power(Rbest, 2))
    #kmax**2 S/N * (m-1/m) * (1/R**2-1)
    kmax = signal / noise * (((nmembers - 1)/nmembers) *
                             (1 / np.power(Rm, 2) - 1))
    #kmax = np.ma.array(kmax, mask=~np.isfinite(kmax))

    # si kmax es amayor a 1 lo fuerzo a que sea 1
    kmax[np.logical_and(np.isfinite(kmax), kmax > 1)] = 1
    #testeo
    K = np.ones_like(kmax)
    #if epsbn is negative spread changes
    K[np.logical_and(np.isfinite(epsbn), epsbn < 0)] = kmax[np.logical_and(np.isfinite(epsbn),
                                                                           epsbn < 0)]
    K = np.repeat(np.repeat(K[np.newaxis, :, :], nmembers,
                            axis=0)[np.newaxis, :, :, :], ntimes,
                  axis=0)
    forecast_inf = forecast * K + (1 - K) *\
            np.rollaxis(np.repeat(em[np.newaxis, :, :, :], nmembers,
                                  axis=0), 1)
    #compute Rbest and epsbn again
    noise = np.nanmean(np.nanvar(forecast_inf, axis=1), axis=0) #noise
    #Rbest = Rm sqrt( 1 + (m/(m - 1) * N) /S )
    Rbest = Rm * np.sqrt(1 + (nmembers / (nmembers - 1) * noise) / signal)
    #epsbest = n/(n-1) * Varobs * (1-Rmean**2)
    epsbn = (ntimes / (ntimes - 1)) *  obs_var * (1 - np.power(Rbest, 2))
    #ahora calculo la regresion
    p = Pool(CORES)
    p.clear()

    if CV_opt: #validacion cruzada ventana 1 anio
        message = "Getting cross-validated forecasts"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        i = np.repeat(np.arange(ntimes, dtype=int), nmembers * nlats * nlons)
        l = np.tile(np.repeat(np.arange(nmembers, dtype=int), nlats* nlons), ntimes)
        j = np.tile(np.repeat(np.arange(nlats, dtype=int), nlons), ntimes * nmembers)
        k = np.tile(np.arange(nlons, dtype=int), ntimes * nmembers * nlats)
        CV_matrix = np.logical_not(np.identity(ntimes))
        def ens_reg(i, l, j, k, CV_m=CV_matrix, obs=observation, forec=forecast_inf):
            if np.logical_or(np.isnan(obs[:, j, k]).all(),
                             np.sum(np.isnan(obs[:, j, k])) / obs.shape[0] > 0.15):
                for_cr = np.nan
            else:
                missing = np.isnan(obs[:, j, k])
                obs_new = obs[np.logical_and(~missing, CV_m[:, i]), j, k]
                y = np.nanmean(forec[:, :, j, k], axis=1)
                y_new = y[np.logical_and(~missing, CV_m[:, i])]
                A = np.vstack([y_new, np.ones(y_new.shape[0])])
                m, c = np.linalg.lstsq(A.T, obs_new, rcond=-1)[0]
                for_cr = m * forec[i, l, j, k] + c
            return for_cr

        res = p.map(ens_reg, i.tolist(), l.tolist(), j.tolist(), k.tolist())
        forecast_cr = np.reshape(np.squeeze(np.stack(res)), [ntimes, nmembers, nlats, nlons])
        del(ens_reg, res)
        p.close()
        return forecast_cr, Rm, Rbest, epsbn, kmax, K
    else:
        message = "Getting hindcast parameters"
        print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
        j = np.repeat(np.arange(nlats, dtype=int), nlons)
        k = np.tile(np.arange(nlons, dtype=int), nlats)
        def ens_reg(j, k, obs=observation, forec=forecast_inf): #forecast 4D
            if np.logical_or(np.isnan(obs[:, j, k]).all(),
                             np.sum(np.isnan(obs[:, j, k])) / obs.shape[0] > 0.15):
                m = np.nan
                c = np.nan
            else:
                missing = np.isnan(obs[:, j, k])
                y = np.nanmean(forec[:, :, j, k], axis=1)
                A = np.vstack([y[~missing], np.ones(y[~missing].shape[0])])
                m, c = np.linalg.lstsq(A.T, obs[~missing, j, k], rcond=-1)[0]
            return m, c
        res = p.map(ens_reg, j.tolist(), k.tolist())
        res = np.stack(res, axis=1)
        a2 = np.reshape(res[0, :], [nlats, nlons])
        b2 = np.reshape(res[1, :], [nlats, nlons])
        del(ens_reg, res)
        p.close()
        return a2, b2, Rm, Rbest, epsbn, kmax, K

def probabilidad_terciles(forecast, epsilon, tercil):
    """computes cpdf until tercile limits"""
    message = "Computing cpdf for tercile limits"
    print(message) if not cfg.get('use_logger') else cfg.logger.info(message)
    if np.ndim(forecast) == 4:
        [ntimes, nmembers, nlats, nlons] = forecast.shape
        i = np.repeat(np.arange(ntimes, dtype=int), nmembers * nlats * nlons)
        l = np.tile(np.repeat(np.arange(nmembers, dtype=int), nlats * nlons),
                    ntimes)
        j = np.tile(np.repeat(np.arange(nlats, dtype=int), nlons),
                    ntimes * nmembers)
        k = np.tile(np.arange(nlons, dtype=int), ntimes * nmembers * nlats)
        p = Pool (CORES)
        p.clear()
        def evaluo_pdf_normal(i, l, j, k, terc=tercil, media=forecast, sigma=epsilon):
            if np.logical_or(np.isnan(media[i, l, j, k]), np.isnan(sigma[j, k])):
                pdf_cdf = np.array([np.nan, np.nan])
            else:
                pdf_cdf = norm.cdf(terc[:, i, j, k], loc=media[i, l, j, k],
                                   scale=np.sqrt(sigma[j, k]))
            return pdf_cdf

        res = p.map(evaluo_pdf_normal, i.tolist(), l.tolist(), j.tolist(),
                    k.tolist())
        p.close()
        prob_terciles = np.rollaxis(np.reshape(np.squeeze(np.stack(res)),
                                               [ntimes, nmembers, nlats, nlons,
                                                2]), 4, 0)
    else:
        [nmembers, nlats, nlons] = forecast.shape
        l = np.repeat(np.arange(nmembers, dtype=int), nlats * nlons)
        j = np.tile(np.repeat(np.arange(nlats, dtype=int), nlons), nmembers)
        k = np.tile(np.arange(nlons, dtype=int), nmembers * nlats)
        p = Pool (CORES)
        p.clear()
        def evaluo_pdf_normal(l, j, k, terc=tercil, media=forecast, sigma=epsilon):
            if np.logical_or(np.isnan(media[l, j, k]), np.isnan(sigma[j, k])):
                pdf_cdf = np.array([np.nan, np.nan])
            else:
                pdf_cdf = norm.cdf(terc[:, j, k], loc=media[l, j, k],
                               scale=np.sqrt(sigma[j, k]))
            return pdf_cdf

        res = p.map(evaluo_pdf_normal, l.tolist(), j.tolist(), k.tolist())
        p.close()
        prob_terciles = np.rollaxis(np.reshape(np.squeeze(np.stack(res)),
                                               [nmembers, nlats, nlons, 2]),
                                    3, 0)

    return prob_terciles

def probabilidad_quintiles(forecast, epsilon, quintil):
    """computes cpdf until quintile limits"""
    print("Computing cpdf for quintile limits")
    if np.ndim(forecast) == 4:
        [ntimes, nmembers, nlats, nlons] = forecast.shape
        i = np.repeat(np.arange(ntimes, dtype=int), nmembers * nlats * nlons)
        l = np.tile(np.repeat(np.arange(nmembers, dtype=int), nlats * nlons),
                    ntimes)
        j = np.tile(np.repeat(np.arange(nlats, dtype=int), nlons),
                    ntimes * nmembers)
        k = np.tile(np.arange(nlons, dtype=int), ntimes * nmembers * nlats)
        p = Pool (CORES)
        p.clear()
        def evaluo_pdf_normal(i, l, j, k, quint=quintil, media=forecast, sigma=epsilon):
            if np.logical_or(np.isnan(media[i, l, j, k]), np.isnan(sigma[j, k])):
                pdf_cdf = np.array([np.nan, np.nan])
            else:
                pdf_cdf = norm.cdf(quint[:, i, j, k], loc=media[i, l, j, k],
                                   scale=np.sqrt(sigma[j, k]))
            return pdf_cdf

        res = p.map(evaluo_pdf_normal, i.tolist(), l.tolist(), j.tolist(),
                    k.tolist())
        p.close()
        prob_quintiles = np.rollaxis(np.reshape(np.squeeze(np.stack(res)),
                                               [ntimes, nmembers, nlats, nlons,
                                                2]), 4, 0)
    else:
        [nmembers, nlats, nlons] = forecast.shape
        l = np.repeat(np.arange(nmembers, dtype=int), nlats * nlons)
        j = np.tile(np.repeat(np.arange(nlats, dtype=int), nlons), nmembers)
        k = np.tile(np.arange(nlons, dtype=int), nmembers * nlats)
        p = Pool (CORES)
        p.clear()
        def evaluo_pdf_normal(l, j, k, quint=quintil, media=forecast, sigma=epsilon):
            if np.logical_or(np.isnan(media[l, j, k]), np.isnan(sigma[j, k])):
                pdf_cdf = np.array([np.nan, np.nan])
            else:
                pdf_cdf = norm.cdf(quint[:, j, k], loc=media[l, j, k],
                               scale=np.sqrt(sigma[j, k]))
            return pdf_cdf

        res = p.map(evaluo_pdf_normal, l.tolist(), j.tolist(), k.tolist())
        p.close()
        prob_quintiles = np.rollaxis(np.reshape(np.squeeze(np.stack(res)),
                                               [nmembers, nlats, nlons, 2]),
                                    3, 0)

    return prob_quintiles
