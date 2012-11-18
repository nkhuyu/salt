{% if salt['runtests.saltsource_on_shared_folders']()==False %}
clean-previous:
  cmd.run:
    - name: rm -rf /salt

download-saltsource:
  file.managed:
    - name: /tmp/saltsource.tar.bz2
    - source: salt://saltsource.tar.bz2
    - replace: True
    - require:
      - cmd: clean-previous

decompress-saltsource:
  cmd.run:
    - cwd: /tmp
    - name: tar jxvf /tmp/saltsource.tar.bz2
    - runas: vagrant
    - require:
      - file: download-saltsource


move-saltsource:
  cmd.run:
    - cwd: /tmp
    - name: mv /tmp/salt-*/ /salt/source
    - require:
      - file: create-salt-dir
      - cmd: decompress-saltsource

create-salt-dir:
  file.directory:
    - name: /salt
    - makedirs: True
    - user: vagrant
    - group: vagrant
    - require:
      - cmd: clean-previous

{% endif %}
