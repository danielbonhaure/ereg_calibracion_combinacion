
import os
import sys

from crontab import CronTab
from getpass import getuser


user_name = getuser()
user_home = os.path.expanduser(f'~{user_name}')
conda_env = os.environ.get('CONDA_DEFAULT_ENV', '')
file_path = os.path.abspath(os.getcwd())


if not conda_env:
    sys.exit('Conda environment not found')


with open(f"{user_home}/.bashrc") as bashrc:
    with open(f"{user_home}/.bashrc_conda", "w") as bashrc_conda:
        start_copy, stop_copy = False, False
        for line in bashrc:
            if ">>> conda initialize >>>" in line:
                start_copy = True
            if start_copy and not stop_copy:
                bashrc_conda.write(line) 
            if "<<< conda initialize <<<" in line:
                stop_copy = True
        if not start_copy and not stop_copy:
            sys.exit('Unrecognized conda configuration')
                
  
with CronTab(user=user_name) as cron:
    
    cron.env['SHELL'] = '/bin/bash'
    cron.env['BASH_ENV'] = f'{user_home}/.bashrc_conda'
    
    py_command = f'cd {file_path} && python download_inputs.py --download operational'
    if not list(cron.find_command(py_command)):
        download_job = cron.new(command=f'conda activate {conda_env} && {py_command} && conda deactivate',
                                comment='Download files from IRIDL')
        download_job.day.on(15,16)

    py_command = f'cd {file_path} && python run_operational_forecast.py'
    if not list(cron.find_command(py_command)):
        forecast_job = cron.new(command=f'conda activate {conda_env} && {py_command} && conda deactivate',
                                comment='Run operational forecast')
        forecast_job.day.on(17)

