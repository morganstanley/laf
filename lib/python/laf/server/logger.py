"""
Log initializer
"""

import logging


def init(logfile=None):
    """
    Initialize logger
    """
    log_format = '[%(asctime)s] [%(filename)s] [%(process)d] '\
                 '[%(levelname)s]: %(message)s'
    logging.basicConfig(format=log_format,
                        filename=logfile,
                        level=logging.INFO,
                        datefmt='%m/%d/%Y %I:%M:%S %p')
