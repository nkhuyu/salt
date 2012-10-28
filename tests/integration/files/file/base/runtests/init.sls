git:
  pkg.installed

supervisor:
  pkg.installed

python-mock:
  pkg.installed

python-virtualenv:
  pkg.installed

{% if grains['os'] not in ('Arch',) %}
  {% if grains['os'] == 'Fedora' %}
python-devel:
  {% else %}
python-dev:
  {% endif %}
  pkg.installed
{% endif %}


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
    - unless: test -d /tmp/ve/bin
    - require:
      - virtualenv: /tmp/ve
      - pkg: supervisor
      - pkg: python-mock

#/home/vagrant/.bashrc:
#  file.append:
#    - text: export PATH=/tmp/ve/bin:$PATH
#    - require:
#      - virtualenv: /tmp/ve

coverage:
  pip.installed:
    - name: coverage
    - runas: vagrant
    - bin_env: /tmp/ve
    - require:
      - pkg: git
    {% if grains['os'] == 'Fedora' %}
      - pkg: python-devel
    {% else %}
      - pkg: python-dev
    {% endif %}
      - virtualenv: /tmp/ve

unittest-xml-reporting:
  pip.installed:
    - runas: vagrant
    - bin_env: /tmp/ve
    - require:
      - virtualenv: /tmp/ve

