bash:
  pkg:
    - installed
  cmd.run:
    - name: sudo sed -i 's/^#force_color_prompt=yes/force_color_prompt=yes/g' /home/vagrant/.bashrc
    - unless: grep '^force_color_prompt=yes' /home/vagrant/.bashrc

bash-completion:
  pkg:
    - installed

# Turn on filetype plugins and remember last position on file
#/etc/bash.bashrc:
  #file.append:
    #- source: salt://bash/bashrc
