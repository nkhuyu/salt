# -*- coding: utf-8 -*-
'''
    salt.log
    ~~~~~~~~

    This is where Salt's logging gets set up. Currently, the required imports
    are made to assure backwards compatibility.


    :codeauthor: :email:`Pedro Algarvio (pedro@algarvio.me)`
    :copyright: © 2013 by the SaltStack Team, see AUTHORS for more details.
    :license: Apache 2.0, see LICENSE for more details.
'''

# Import severals classes/functions from salt.log.config for backwards
# compatibility
from salt.log.config import (
    LOG_LEVELS,
    SORTED_LEVEL_NAMES,
    is_console_configured,
    is_logfile_configured,
    is_logging_configured,
    is_temp_logging_configured,
    setup_temp_logger,
    setup_console_logger,
    setup_logfile_logger,
    set_logger_level,
)
