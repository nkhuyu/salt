# Everyone needs vim installed!

vim:
  pkg:
    - installed

# Turn on filetype plugins and remember last position on file
/etc/vim/vimrc.local:
  file:
    - managed
    - source: salt://editors/vim/vimrc.local
    - user: root
    - group: root
    - mode: 644
    - require:
      - pkg: vim