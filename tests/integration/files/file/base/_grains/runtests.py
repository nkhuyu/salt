# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 fenc=utf-8
"""
    :copyright: © 2012 UfSoft.org - :email:`Pedro Algarvio (pedro@algarvio.me)`
    :license: Apache 2.0, see LICENSE for more details
"""

import sys


runtests = {}
grains = {'runtests': runtests}

def __virtual__():
    if __grains__.get('id') not in ('minion', 'sub_minion'):
        return 'runtests'
    return None


def py_version_info():
    runtests['py_version_info'] = tuple(sys.version_info[:3])


def virtualenv_has_system_site_packages():
    try:
        import virtualenv
    except ImportError:
        return

    try:
        venv_version = virtualenv.__version__.split('.')
    except AttributeError:
        venv_version = virtualenv.virtualenv_version.split('.')

    venv_version = tuple([int(i) for i in venv_version])

    runtests['virtualenv_has_system_site_packages'] = venv_version >= (2, 7)
    return grains
