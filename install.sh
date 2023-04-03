#!/bin/sh

if ! [ -x "$(command -v mn)" ]; then
    INSTALLPATH=$(pwd)
    sudo apt update
    sudo apt install -y libffi-dev pkg-config mariadb-server makeself
    cd ~/
    git clone https://github.com/mininet/mininet
    cd mininet/
    git checkout -b mininet-2.3.1b1 2.3.1b1
    cd ~/
    sudo PYTHON=python3 ~/mininet/util/install.sh -nv
    cd $INSTALLPATH/
    sudo apt-get -y install python3-mysqldb
    sudo apt-get install -y libhdf5-100 libhdf5-dev
    make pymodbus-install
    make first-run
    sudo python3 -m pip install -r requirements.txt
    #sudo python -m ipmininet.install -af
fi

sudo mn --test pingall
echo 'Installation complete.'
