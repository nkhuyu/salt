git:
  # Git is necessary for 've-saltdevel-install' or else pip.freeze will fail.
  pkg.installed

supervisor:
  pkg.installed

python-mock:
  pkg.installed

python-virtualenv:
  pkg.installed

python-dev:
  pkg.installed

python-xmlrunner:
  pkg.installed

/tmp/ve:
  virtualenv.manage:
    - runas: vagrant
    - distribute: True
    - no_site_packages: False
    - system_site_packages: True
    - mirrors: http://testpypi.python.org/pypi
    - require:
      - pkg: python-virtualenv

ve-saltdevel-install:
  cmd.run:
    - cwd: /salt/source/
    - env: USE_SETUPTOOLS=1
    - mirrors: http://testpypi.python.org/pypi
    - name: sudo USE_SETUPTOOLS=1 /tmp/ve/bin/python setup.py develop
    - runas: vagrant
    - require:
      - virtualenv: /tmp/ve
      - pkg: supervisor
      - pkg: python-mock

/home/vagrant/.bashrc:
  file.append:
    - text: export PATH=/tmp/ve/bin:$PATH
    - require:
      - virtualenv: /tmp/ve

coverage:
  pip.installed:
    - name: coverage
    - runas: vagrant
    - bin_env: /tmp/ve
    - require:
      - pkg: git
      - pkg: python-dev
      - virtualenv: /tmp/ve

salt-minion:
  service:
    - mod_watch
    - full_restart: True
