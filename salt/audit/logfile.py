# -*- coding: utf-8 -*-
'''
    salt.audit.logfile
    ~~~~~~~~~~~~~~~~~~

    Logfile auditor.

    :codeauthor: :email:`Pedro Algarvio (pedro@algarvio.me)`
    :copyright: © 2013 by the SaltStack Team, see AUTHORS for more details.
    :license: Apache 2.0, see LICENSE for more details.
'''

# Import python libs
import logging

# Import salt libs
import salt.log

log = logging.getLogger(__name__)


def __virtual__():
    '''
    Only load if enabled
    '''
    if 'logfile' not in __opts__['auditors']:
        log.debug('Logfile audit logging not enabled in configured auditors')
        return False

    audit_log_file = __opts__.get('audit_log_file', None)
    if not audit_log_file:
        log.debug(
            'Logfile audit logging not enabled because \'audit_log_file\' is '
            '{0!r}'.format(audit_log_file)
        )
        return False

    return True


def __init__():
    '''
    Setup the log file audit
    '''
    # Were are we logging to?
    audit_log_file = __opts__.get('audit_log_file', None)
    if audit_log_file:
        log.debug('Not configuring audit logging')
        return

    handler = salt.log._setup_logfile_handler(__opts__['audit_log_file'])
    handler.setLevel(salt.log.AUDIT)
    handler.addFilter(AuditLoggingFilter())
    logging.getLogger().addHandler(handler)


def audit():
    ''''
    The audit function still lacking it's arguments....
    ''''


class AuditLoggingFilter(logging.Filter):
    '''
    Custom logging filter which will only allow log records with the AUDIT
    logging level to be logged.
    '''
    def filter(self, record):
        return record.levelno == salt.log.AUDIT
