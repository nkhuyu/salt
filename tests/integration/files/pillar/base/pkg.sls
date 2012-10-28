pkg:
  {% if grains['os_family'] == 'RedHat' %}
  vim: vim-enhanced
  supervisor: supervisor
  python-mock: python-mock
  python-virtualenv: python-virtualenv

    {% if grains['os'] == 'Fedora' %}
  python-dev: python-devel
    {% else %}
  python-dev: libpython-devel
    {% endif %}

  {% if grains['os_family'] == 'Debian' %}
  vim: vim
  supervisor: supervisor
  python-mock: python-mock
  python-virtualenv: python-virtualenv
  python-dev: python-dev

  {% elif grains['os'] == 'Arch' %}
  vim: vim
  supervisor: supervisor
  python-mock: python2-mock
  python-virtualenv: python-virtualenv

  {% elif grains['os'] == 'Gentoo' %}
  vim: vim

  {% elif grains['os'] == 'FreeBSD' %}
  vim: vim

  {% else %}
  vim: vim

  {% endif %}
