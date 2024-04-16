
import os
import sys

from getpass import getuser


user_name = getuser()
user_home = os.path.expanduser(f'~{user_name}')
conda_env = os.environ.get('CONDA_DEFAULT_ENV', '')
file_path = os.path.abspath(os.getcwd())

print(user_name, user_home, conda_env, file_path)

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

cron_commands = [
    f'cd {file_path} && python download_inputs.py --download operational',
    f'cd {file_path} && python run_operational_forecast.py'
]

cron_timings = [
    '0 0 15,16 * *',  # For the first command, run on 15th and 16th day of the month
    '0 0 17 * * '      # For the second command, run on 17th day of the month
]

# Setup cron jobs
for command, timing in zip(cron_commands, cron_timings):
    cron_command = f'(source {os.path.expanduser("~")}/.bashrc_conda && conda activate {conda_env} && {command})'
    os.system(f'(crontab -u {user_name} -l ; echo "{timing} {cron_command}") | crontab -u {user_name} -')


