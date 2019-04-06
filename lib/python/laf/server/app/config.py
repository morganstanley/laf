"""
Load family configuration
"""
import json
import os
import logging

_LOG = logging.getLogger(__name__)

LAFSVR_FAMILY_FILE = 'etc/family'


def get_laf_family(basedir):
    """
    Get family name from the etc/family file in basedir
    """
    familyfile = os.path.join(basedir, LAFSVR_FAMILY_FILE)
    with open(familyfile) as fh:
        family = fh.read().rstrip()
    if family is None:
        raise Exception('Family file etc/family is missing from config')
    return family


def get_lone_cfg(basedir, options):
    """
    Get the lone configuration
    """
    lafconfig = dict()
    if 'env' in options:
        lafconfig['env'] = options['env']
    if 'deployment' in options:
        lafconfig['deployment'] = options['deployment']
    else:
        lafconfig['deployment'] = 'prod'
    lafconfig['family'] = get_laf_family(basedir)
    corebase = os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(__file__)))))
    lafconfig['basedir'] = basedir
    if 'mode' in options:
        lafconfig['mode'] = options['mode']
    else:
        lafconfig['mode'] = 'client'
    lafconfig['corebase'] = corebase
    if 'servers' in options:
        lafconfig['servers'] = options['servers']
    if 'LAF_CONFIG' in os.environ:
        family_config_dir = os.environ['LAF_CONFIG']
        family_name = '#'.join(lafconfig['family'].split('/'))
        family_name = family_name + '#' + lafconfig['deployment']
        cfgfilename = 'config-{0}.json'.format(family_name)
        config_file = os.path.join(family_config_dir, cfgfilename)
        try:
            with open(config_file) as infile:
                family_cfg = json.load(infile)
                for key, value in family_cfg.items():
                    lafconfig[key] = value
        except FileNotFoundError:
            raise Exception('Invalid deployment for the family')
    return lafconfig
