
##################################################################
##                           README                             ##
##################################################################
## Este Dockerfile permite crear un contendor con todos los pa- ##
## quetes y todas las configuraciones necesarias para calibrar  ##
## pronósticos utilizando Ensemble Regression (EREG).           ##
##################################################################



##########################
## Set GLOBAL arguments ##
##########################

# Set python version
ARG PYTHON_VERSION="3.12"

# Set EREG installation folder
ARG EREG_HOME="/opt/ereg"

# Set EREG data folder
ARG EREG_DATA="/data/ereg"

# Set global CRON args
ARG D_CRON_TIME_STR="0 0 15,16 * *"
ARG R_CRON_TIME_STR="0 0 17 * *"

# Set Pycharm version
ARG PYCHARM_VERSION="2023.1"



######################################
## Stage 1: Install Python packages ##
######################################

# Create image
FROM python:${PYTHON_VERSION}-slim AS py_builder

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Set python environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install OS packages
RUN apt-get -y -qq update && \
    apt-get -y -qq upgrade && \
    apt-get -y -qq --no-install-recommends install \
        build-essential \
        # some project dependencies \
        cdo nco \
        # to install numpy dependencies (ninja and patchelf)
        cmake automake \
        # to install cartopy
        proj-bin libproj-dev libgeos-dev && \
    rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /usr/src/app

# Upgrade pip and install dependencies
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels \
        numpy \
        dask \
        xarray \
        scipy \
        astropy \
        matplotlib \
        pathos \
        netcdf4 \
        cdo \
        nco \
        python-crontab \
        PyYAML \
        redis[hiredis]
# Install shapely and Cartopy (shapely is a dependency of Cartopy)
RUN python3 -m pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels \
        shapely Cartopy



###############################################
## Stage 2: Copy Python installation folders ##
###############################################

# Create image
FROM python:${PYTHON_VERSION}-slim AS py_final

# set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Install OS packages
RUN apt-get -y -qq update && \
    apt-get -y -qq upgrade && \
    apt-get -y -qq --no-install-recommends install \
        # some project dependencies \
        cdo nco \
        # to be able to use cartopy (Python)
        proj-bin libproj-dev libgeos-dev && \
    rm -rf /var/lib/apt/lists/*

# Install python dependencies from py_builder
COPY --from=py_builder /usr/src/app/wheels /wheels
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install --no-cache /wheels/* && \
    rm -rf /wheels



################################
## Stage 3: Create EREG image ##
################################

# Create EREG image
FROM py_final AS ereg_builder

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Load EREG ARGs
ARG EREG_HOME
ARG EREG_DATA

# Create EREG_HOME folder
RUN mkdir -p ${EREG_HOME}

# Copy project
COPY *.py ${EREG_HOME}
COPY *.sh ${EREG_HOME}
COPY *.md ${EREG_HOME}
COPY *.yaml ${EREG_HOME}
COPY *.yaml.tmpl ${EREG_HOME}
COPY combined_models ${EREG_HOME}
COPY updates ${EREG_HOME}

# Disable group switching
RUN sed -i "s/^group_for_files/# group_for_files/g" ${EREG_HOME}/config.yaml

# Change download_folder and gen_data_folder
RUN sed -i -E "s|^(\s+download_folder:).*$|\1 ${EREG_DATA}/descargas/|g" ${EREG_HOME}/config.yaml
RUN sed -i -E "s|^(\s+gen_data_folder:).*$|\1 ${EREG_DATA}/generados/|g" ${EREG_HOME}/config.yaml

# Create input and output folders (these folders are too big so they must be used them as volumes)
RUN mkdir -p ${EREG_DATA}/descargas
RUN mkdir -p ${EREG_DATA}/generados

# Save Git commit hash of this build into ${EREG_HOME}/repo_version.
# https://github.com/docker/hub-feedback/issues/600#issuecomment-475941394
# https://docs.docker.com/build/building/context/#keep-git-directory
COPY ./.git /tmp/git
RUN export head=$(cat /tmp/git/HEAD | cut -d' ' -f2) && \
    if echo "${head}" | grep -q "refs/heads"; then \
    export hash=$(cat /tmp/git/${head}); else export hash=${head}; fi && \
    echo "${hash}" > ${EREG_HOME}/repo_version && rm -rf /tmp/git

# Set permissions of app files
RUN chmod -R ug+rw,o+r ${EREG_HOME}
RUN chmod -R ug+rw,o+r ${EREG_DATA}



###########################################
## Stage 4: Install management packages  ##
###########################################

# Create image
FROM ereg_builder AS ereg_mgmt

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Install OS packages
RUN apt-get -y -qq update && \
    apt-get -y -qq upgrade && \
    apt-get -y -qq --no-install-recommends install \
        # install Tini (https://github.com/krallin/tini#using-tini)
        tini \
        # to see process with pid 1
        htop procps \
        # to allow edit files
        vim \
        # to manually download input files
        wget \
        # to run process with cron
        cron && \
    rm -rf /var/lib/apt/lists/*

# Setup cron to allow it run as a non root user
RUN chmod u+s $(which cron)

# Add Tini (https://github.com/krallin/tini#using-tini)
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]



####################################
## Stage 5: Setup EREG core image ##
####################################

# Create image
FROM ereg_mgmt AS ereg-core

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Renew EREG ARGs
ARG EREG_HOME
ARG EREG_DATA

# Renew USER ARGs
ARG USR_NAME
ARG GRP_NAME

# Renew CRON ARGs
ARG D_CRON_TIME_STR
ARG R_CRON_TIME_STR

# Install OS packages
RUN apt-get -y -qq update && \
    apt-get -y -qq upgrade && \
    apt-get -y -qq --no-install-recommends install \
        # to check container health
        redis-tools && \
    rm -rf /var/lib/apt/lists/*

# Set read-only environment variables
ENV EREG_HOME=${EREG_HOME}
ENV EREG_DATA=${EREG_DATA}

# Set environment variables
ENV D_CRON_TIME_STR=${D_CRON_TIME_STR}
ENV R_CRON_TIME_STR=${R_CRON_TIME_STR}

# Definir comandos para descarga y calibración de pronósticos
ARG DOWNLOAD_1_CMD="/usr/local/bin/python download_inputs.py --download real_time --re-check"
ARG DOWNLOAD_2_CMD="/usr/local/bin/python download_inputs.py --download operational --re-check"
ARG RUN_PYTHON_CMD="/usr/local/bin/python run_operational_forecast.py --overwrite --combination wsereg --weighting mean_cor --ignore-plotting"

# Crear archivo de configuración de CRON
RUN printf "\n\
\043 Download input data \n\
${D_CRON_TIME_STR}  cd ${EREG_HOME} && ${DOWNLOAD_1_CMD} >> /proc/1/fd/1 2>> /proc/1/fd/1 \n\
${D_CRON_TIME_STR}  cd ${EREG_HOME} && ${DOWNLOAD_2_CMD} >> /proc/1/fd/1 2>> /proc/1/fd/1 \n\
\043 Run operational forecasts \n\
${R_CRON_TIME_STR}  cd ${EREG_HOME} && ${RUN_PYTHON_CMD} >> /proc/1/fd/1 2>> /proc/1/fd/1 \n\
\n" > ${EREG_HOME}/crontab.conf
RUN chmod a+rw ${EREG_HOME}/crontab.conf

# Crear archivo con variables de entorno
RUN touch ${EREG_HOME}/crontab-envvars.txt \
 && chmod a+rw ${EREG_HOME}/crontab-envvars.txt

# CRON toma variables de entorno desde /etc/environment,
# para más info ver: https://askubuntu.com/a/700126
RUN mv /etc/environment /etc/environment-old \
 && ln -s ${EREG_HOME}/crontab-envvars.txt /etc/environment

# Setup CRON for root user
RUN (cat ${EREG_HOME}/crontab.conf) | crontab -

# Crear script de inicio.
RUN printf "#!/bin/bash \n\
set -e \n\
\n\
\043 Reemplazar tiempo ejecución de la descarga de los datos de entrada \n\
crontab -l | sed \"/download_inputs.py/ s|^\S* \S* \S* \S* \S*|\$D_CRON_TIME_STR|g\" | crontab - \n\
crontab -l | sed \"/run_operational_forecast.py/ s|^\S* \S* \S* \S* \S*|\$R_CRON_TIME_STR|g\" | crontab - \n\
\n\
\043 Copiar variables de entorno del contenedor a /etc/environment \n\
xargs --null --max-args=1 --arg-file=/proc/1/environ > ${EREG_HOME}/crontab-envvars.txt \n\
\n\
\043 Ejecutar cron \n\
cron -fL 15 \n\
\n" > /startup.sh
RUN chmod a+x /startup.sh

# Create script to check container health
RUN printf "#!/bin/bash\n\
if [ \$(find ${EREG_HOME} -type f -name '*.pid' 2>/dev/null | wc -l) != 0 ] || \n\
   [ \$(echo 'KEYS *' | redis-cli -h \${REDIS_HOST} 2>/dev/null | grep -c ereg) != 0 ] && \n\
   [ \$(ps -ef | grep -v 'grep' | grep -c 'python') == 0 ] \n\
then \n\
  exit 1 \n\
else \n\
  exit 0 \n\
fi \n\
\n" > /check-healthy.sh
RUN chmod a+x /check-healthy.sh

# Run your program under Tini (https://github.com/krallin/tini#using-tini)
CMD [ "bash", "-c", "/startup.sh" ]
# or docker run your-image /your/program ...

# Verificar si hubo alguna falla en la ejecución del replicador
HEALTHCHECK --interval=3s --timeout=3s --retries=3 CMD bash /check-healthy.sh



#####################################################
## Usage: Commands to Build and Run this container ##
#####################################################


# CONSTRUIR IMAGEN (CORE)
# docker build --force-rm \
#   --target ereg-core \
#   --tag ghcr.io/danielbonhaure/ereg_calibracion_combinacion:ereg-core-v1.0 \
#   --build-arg D_CRON_TIME_STR="0 0 15,16 * *" \
#   --build-arg R_CRON_TIME_STR="0 0 17 * *" \
#   --file Dockerfile .

# LEVANTAR IMAGEN A GHCR
# docker push ghcr.io/danielbonhaure/ereg_calibracion_combinacion:ereg-core-v1.0

# CORRER OPERACIONALMENTE CON CRON
# docker run --name ereg \
#   --mount type=bind,src=/data/ereg/descargas,dst=/data/ereg/descargas \
#   --mount type=bind,src=/data/ereg/generados,dst=/data/ereg/generados \
#   --env DROP_COMBINED_FORECASTS='YES' --memory="4g" \
#   --detach ghcr.io/danielbonhaure/ereg_calibracion_combinacion:ereg-core-v1.0

# CORRER MANUALMENTE EN PRIMER PLANO Y BORRANDO EL CONTENEDOR AL FINALIZAR
# docker run --name ereg \
#   --mount type=bind,src=/data/ereg/descargas,dst=/data/ereg/descargas \
#   --mount type=bind,src=/data/ereg/generados,dst=/data/ereg/generados \
#   --env DROP_COMBINED_FORECASTS='YES' --memory="4g" \
#   --rm ghcr.io/danielbonhaure/ereg_calibracion_combinacion:ereg-core-v1.0 \
# python /opt/ereg/<script> <args>

# CORRER MANUALMENTE EN SEGUNDO PLANO Y SIN BORRAR EL CONTENEDOR AL FINALIZAR
# NO BORRAR EL CONTENEDOR AL FINALIZAR PERMITE VER LOS ERRORES (EN CASO QUE HAYA ALGUNO)
# docker run --name ereg \
#   --mount type=bind,src=/data/ereg/descargas,dst=/data/ereg/descargas \
#   --mount type=bind,src=/data/ereg/generados,dst=/data/ereg/generados \
#   --env DROP_COMBINED_FORECASTS='YES' --memory="4g" \
#   --detach ghcr.io/danielbonhaure/ereg_calibracion_combinacion:ereg-core-v1.0 \
# python /opt/ereg/<script> <args>


# VER RAM USADA POR LOS CONTENEDORES CORRIENDO
# docker stats --format "table {{.ID}}\t{{.Name}}\t{{.CPUPerc}}\t{{.PIDs}}\t{{.MemUsage}}" --no-stream

# VER LOGS (CON COLORES) DE CONTENEDOR CORRIENDO EN SEGUNDO PLANO
# docker logs --follow ereg 2>&1 | ccze -m ansi


#
# README
#
# El parámetro " --env DROP_COMBINED_FORECASTS='YES' " crea una variable de entorno en el OS del contenedor
# que establece la respuesta a la siguiente pregunta lanzada por EREG cuando es corrido fuera de un contenedor:
# --> Model/s was added or deleted. Do you want to drop current combined forecasts and update combined_models file?
# Esta pregunta es lanzada solo cuando se detecta que han sido modificados los modelos a ser combinados. Responder
# a esta pregunta con un NO implica que no se actualizarán los modelos utilizados para la calibración, es decir, que
# EREG se seguirá ejecutando utilizando los archivos de calibración producidos antes del cambio detectado en los
# modelos a ser combiandos. Es importante tener en cuenta que el comportamiento por defecto ante esta situación es no
# borrar los archivos de calibración!! Esto para evitar el borrado accidental de los mismos, puesto que producirlos es
# lleva bastante tiempo, principalmente para el periodo retrospectivo o hindcast.
#
