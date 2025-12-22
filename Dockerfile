
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

# Set Python version
ARG PYTHON_VERSION="3.12"

# Set Python image variant
ARG IMG_VARIANT="-slim"

# Set EREG installation folder
ARG EREG_HOME="/opt/ereg"

# Set EREG data folder
ARG EREG_DATA="/data/ereg"

# Set global CRON args
ARG D_CRON_TIME_STR="0 0 15,16 * *"
ARG R_CRON_TIME_STR="0 0 17 * *"



######################################
## Stage 1: Install Python packages ##
######################################

# Create image
FROM python:${PYTHON_VERSION}${IMG_VARIANT} AS py_builder

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Set python environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install OS packages
RUN apt-get --quiet --assume-yes update && \
    apt-get --quiet --assume-yes upgrade && \
    apt-get --quiet --assume-yes --no-install-recommends install \
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
    python3 -m pip wheel --no-cache-dir --no-deps \
    --wheel-dir /usr/src/app/wheels \
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
RUN python3 -m pip wheel --no-cache-dir --no-deps \
    --wheel-dir /usr/src/app/wheels \
        shapely \
        Cartopy



###############################################
## Stage 2: Copy Python installation folders ##
###############################################

# Create image
FROM python:${PYTHON_VERSION}${IMG_VARIANT} AS py_final

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Install OS packages
RUN apt-get --quiet --assume-yes update && \
    apt-get --quiet --assume-yes upgrade && \
    apt-get --quiet --assume-yes --no-install-recommends install \
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



##########################################
## Stage 3: Install management packages ##
##########################################

# Create image
FROM py_final AS base_image

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Install OS packages
RUN apt-get --quiet --assume-yes update && \
    apt-get --quiet --assume-yes --no-install-recommends install \
        # install Tini (https://github.com/krallin/tini#using-tini)
        tini \
        # to see process with pid 1
        htop procps \
        # to allow edit files
        vim \
        # to manually download input files
        curl wget \
        # to run process with cron
        cron && \
    rm -rf /var/lib/apt/lists/*

# Create utils directory
RUN mkdir -p /opt/utils

# Create script to load environment variables
RUN printf "#!/bin/bash \n\
export \$(cat /proc/1/environ | tr '\0' '\n' | xargs -0 -I {} echo \"{}\") \n\
\n" > /opt/utils/load-envvars

# Create startup/entrypoint script
RUN printf "#!/bin/bash \n\
set -e \n\
\043 https://docs.docker.com/reference/dockerfile/#entrypoint \n\
exec \"\$@\" \n\
\n" > /opt/utils/entrypoint

# Create script to check the container's health
RUN printf "#!/bin/bash \n\
exit 0 \n\
\n" > /opt/utils/check-healthy

# Set minimal permissions to the utils scripts
RUN chmod --recursive u=rx,g=rx,o=rx /opt/utils

# Allows utils scripts to run as a non-root user
RUN chmod u+s /opt/utils/load-envvars

# Setup cron to allow it to run as a non-root user
RUN chmod u+s $(which cron)

# Add Tini (https://github.com/krallin/tini#using-tini)
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]



################################
## Stage 4: Create EREG image ##
################################

# Create EREG image
FROM base_image AS ereg_builder

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Install OS packages
RUN apt-get --quiet --assume-yes update && \
    apt-get --quiet --assume-yes --no-install-recommends install \
        # to save scripts PID
        # to check container health
        redis-tools && \
    rm -rf /var/lib/apt/lists/*

# Renew ARGs
ARG EREG_HOME
ARG EREG_DATA

# Create EREG_HOME folder
RUN mkdir -p ${EREG_HOME}

# Copy EREG code
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

# Set minimum required permissions for files and folders
RUN find ${EREG_HOME} ${EREG_DATA} -type f -exec chmod -R u=rw,g=rw,o=r -- {} + && \
    find ${EREG_HOME} ${EREG_DATA} -type d -exec chmod -R u=rwx,g=rwx,o=rx -- {} +



####################################
## Stage 5: Setup EREG core image ##
####################################

# Create image
FROM ereg_builder AS ereg_core

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Renew ARGs
ARG EREG_HOME
ARG EREG_DATA
ARG D_CRON_TIME_STR
ARG R_CRON_TIME_STR

# Install OS packages
RUN apt-get --quiet --assume-yes update && \
    apt-get --quiet --assume-yes --no-install-recommends install \
        # to configure locale
        locales && \
    rm -rf /var/lib/apt/lists/*

# Configure Locale en_US.UTF-8
RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    sed -i -e 's/# es_US.UTF-8 UTF-8/es_US.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales

# Set locale
ENV LC_ALL=en_US.UTF-8

# Definir comandos para descarga y calibración de pronósticos
ARG DOWNLOAD_1_CMD="/usr/local/bin/python download_inputs.py --download real_time --re-check"
ARG DOWNLOAD_2_CMD="/usr/local/bin/python download_inputs.py --download operational --re-check"
ARG RUN_PYTHON_CMD="/usr/local/bin/python run_operational_forecast.py --overwrite --combination wsereg --weighting mean_cor --ignore-plotting"

# Create CRON configuration file
RUN printf "\n\
SHELL=/bin/bash \n\
BASH_ENV=/opt/utils/load-envvars \n\
\n\
\043 Download input data \n\
${D_CRON_TIME_STR}  (cd ${EREG_HOME} && ${DOWNLOAD_1_CMD} >> /proc/1/fd/1 2>> /proc/1/fd/1) \n\
${D_CRON_TIME_STR}  (cd ${EREG_HOME} && ${DOWNLOAD_2_CMD} >> /proc/1/fd/1 2>> /proc/1/fd/1) \n\
\043 Run operational forecasts \n\
${R_CRON_TIME_STR}  (cd ${EREG_HOME} && ${RUN_PYTHON_CMD} >> /proc/1/fd/1 2>> /proc/1/fd/1) \n\
\n" > ${EREG_HOME}/crontab.conf

# Create startup/entrypoint script
RUN printf "#!/bin/bash \n\
set -e \n\
\n\
\043 Reemplazar tiempo ejecución de la descarga de los datos de entrada \n\
sed -i \"/download_inputs.py/ s|^\d\S+\s\S+\s\S+\s\S+\s\S+\s|\$D_CRON_TIME_STR|g\" /opt/utils/crontab.conf \n\
crontab -l | sed \"/download_inputs.py/ s|^\d\S+\s\S+\s\S+\s\S+\s\S+\s|\$D_CRON_TIME_STR|g\" | crontab - \n\
sed -i \"/run_operational_forecast.py/ s|^\d\S+\s\S+\s\S+\s\S+\s\S+\s|\$R_CRON_TIME_STR|g\" /opt/utils/crontab.conf \n\
crontab -l | sed \"/run_operational_forecast.py/ s|^\d\S+\s\S+\s\S+\s\S+\s\S+\s|\$R_CRON_TIME_STR|g\" | crontab - \n\
\n\
exec \"\$@\" \n\
\n" > /opt/utils/entrypoint

# Create script to check the container's health
RUN printf "#!/bin/bash\n\
if [ \$(find ${EREG_HOME} -type f -name '*.pid' 2>/dev/null | wc -l) != 0 ] || \n\
   [ \$(echo 'KEYS *' | redis-cli -h \${REDIS_HOST} 2>/dev/null | grep -c ereg) != 0 ] && \n\
   [ \$(ps -ef | grep -v 'grep' | grep -c 'python') == 0 ] \n\
then \n\
  exit 1 \n\
else \n\
  exit 0 \n\
fi \n\
\n" > /opt/utils/check-healthy

# Set minimal permissions to the new scripts and files
RUN chmod u=rw,g=r,o=r ${EREG_HOME}/crontab.conf

# Set read-only environment variables
ENV EREG_HOME=${EREG_HOME}
ENV EREG_DATA=${EREG_DATA}

# Set user-definable environment variables
ENV D_CRON_TIME_STR=${D_CRON_TIME_STR}
ENV R_CRON_TIME_STR=${R_CRON_TIME_STR}

# Declare optional environment variables
ENV REDIS_HOST=localhost



#####################################
## Stage 6: Setup EREG final image ##
#####################################

# Create image
FROM ereg_core AS ereg-root

# Set environment variables
ARG DEBIAN_FRONTEND=noninteractive

# Renew ARGs
ARG EREG_HOME

# Setup CRON for root user
RUN (cat ${EREG_HOME}/crontab.conf) | crontab -

# Create standard directories used for specific types of user-specific data, as defined 
# by the XDG Base Directory Specification. For when "docker run --user uid:gid" is used.
# OBS: don't forget to add --env HOME=/home when running the container.
RUN mkdir -p /home/.local/share && \
    mkdir -p /home/.cache && \
    mkdir -p /home/.config
# Set permissions, for when "docker run --user uid:gid" is used
RUN chmod -R a+rwx /home/.local /home/.cache /home/.config

# Add Tini (https://github.com/krallin/tini#using-tini)
ENTRYPOINT [ "/usr/bin/tini", "-g", "--", "/opt/utils/entrypoint" ]

# Run your program under Tini (https://github.com/krallin/tini#using-tini)
CMD [ "cron", "-fL", "15" ]
# or docker run your-image /your/program ...

# Configurar verificación de la salud del contenedor
HEALTHCHECK --interval=3s --timeout=3s --retries=3 CMD bash /opt/utils/check-healthy

# Set work directory
WORKDIR ${EREG_HOME}



#####################################################
## Usage: Commands to Build and Run this container ##
#####################################################


# CONSTRUIR IMAGEN (CORE)
# docker build --force-rm \
#   --target ereg-root \
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
