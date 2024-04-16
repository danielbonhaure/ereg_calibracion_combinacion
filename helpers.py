#!/usr/bin/env python

import locale
import sys
import smtplib

from contextlib import contextmanager
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


@contextmanager
def localized(code):
    old_code, old_encoding = locale.getlocale()
    locale.setlocale(locale.LC_ALL, code)
    yield
    locale.setlocale(locale.LC_ALL, f"{old_code}.{old_encoding}")
  

def send_email(from_addr, password, to_addrs: list, subject, body):
    message = MIMEMultipart()
    message['Subject'] = subject
    message['From'] = from_addr
    message['To'] = ', '.join(to_addrs)

    body_content = body
    message.attach(MIMEText(body_content, "html"))
    msg_body = message.as_string()

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(from_addr, password)
    server.sendmail(from_addr, to_addrs, msg_body)
    server.quit()


class ProgressBar:

    def __init__(self, total_count: int, status_tml: str, bar_length: int = 70):
        self.actual_count: float = 0
        self.total_count: int = total_count
        self.status_tml: str = status_tml
        self.bar_length: int = bar_length

    def __refresh__(self):
        filled_len = int(round(self.bar_length * self.actual_count / float(self.total_count)))

        percents = round(100.0 * self.actual_count / float(self.total_count), 1)
        bar = '=' * filled_len + '-' * (self.bar_length - filled_len)

        sys.stdout.write(f'[{bar}] {percents}% ...{self.status_tml}\r')
        sys.stdout.flush()

    def report_advance(self, advance_count: float):
        self.actual_count += advance_count
        self.__refresh__()

    def update_count(self, actual_count: float):
        self.actual_count = actual_count
        self.__refresh__()

    @staticmethod
    def up():
        sys.stdout.write('\x1b[1A')
        sys.stdout.flush()

    @staticmethod
    def down():
        sys.stdout.write('\n')
        sys.stdout.flush()

    @staticmethod
    def clear_line():
        sys.stdout.write("\033[K")
        sys.stdout.flush()

    def open(self):
        self.update_count(0)

    @staticmethod
    def pin_up():
        sys.stdout.write('\n')

    @staticmethod
    def close():
        sys.stdout.write('\n')


class DownloadProgressBar:
    def __init__(self, file_name, bar_length: int = 70):
        self.pbar = None
        self.fnme = file_name
        self.blen = bar_length

    def __call__(self, block_num, block_size, total_size):
        if not self.pbar:
            self.pbar = ProgressBar(total_size, f"Downloading file: {self.fnme}", self.blen)
            self.pbar.down()

        downloaded = block_num * block_size

        if downloaded > total_size:
            downloaded = total_size

        advance = downloaded - self.pbar.actual_count
        self.pbar.report_advance(advance)

        if downloaded == total_size:
            self.pbar.clear_line()
            self.pbar.up()


class SecondaryProgressBar(ProgressBar):

    def open(self):
        self.down()
        super().open()

    def close(self):
        self.clear_line()
        self.up()
