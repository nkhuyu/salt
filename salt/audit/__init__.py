# -*- coding: utf-8 -*-
'''
    salt.audit
    ~~~~~~~~~~

    This module will be responsible for gathering audit data form salt.

    :codeauthor: :email:`Pedro Algarvio (pedro@algarvio.me)`
    :copyright: © 2013 by the SaltStack Team, see AUTHORS for more details.
    :license: Apache 2.0, see LICENSE for more details.
'''

# Import python libs
import logging

# Import salt libs
import salt.loader


log = logging.getLogger(__name__)


class Auditor(object):
    '''
    Create an auditor wrapper object that wraps the audit functions and
    iterates over them.
    '''
    def __init__(self, opts):
        self.opts = opts
        self.auditors = salt.loader.fileserver(opts, opts['auditors'])
