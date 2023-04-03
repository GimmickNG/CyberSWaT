export PYTHONIOENCODING := utf-8
.DEFAULT_GOAL := run

# VARIABLES {{{1

# The default (temporary) pycopy build directory. Will be created if it does not exist, and
# **WILL BE DELETED** after use. Do NOT use a directory that contains important files!
PYCOPY_BUILD_DIR ?= .pycopy_build

UMODBUS_BUILD_DIR ?= pycopy-tools

# PYCOPY_STDLIB contains the names of pycopy libraries in the 'pycopy-lib' repository
# but is restricted to those that do not have any extra dependencies - so even though
# random, struct, time and socket are in pycopy-lib, they cannot be installed just by
# copying into the modules/ folder - upip will need to install it + its dependencies.
PYCOPY_STDLIB ?= ffilib logging typing argparse signal

HISTORIAN_PORT ?= 8080
HISTORIAN_IP ?= 192.168.1.4
HISTORIAN_PARAMS ?= autoLoginUsername=admin&autoLoginPassword=changeme
HISTORIAN_URL = 'http://$(HISTORIAN_IP):$(HISTORIAN_PORT)/ui/?$(HISTORIAN_PARAMS)'
MANGO_DIR = /opt/mango/bin
PYTHON = python3

clear:
	clear

clean-simulation:
	@# cd historian && make clean
	if [ -e /etc/hosts.bak ]; then \
		sudo mv /etc/hosts.bak /etc/hosts; \
	fi
	sudo find . -name "*.pyc" -exec rm -f {} \;
	sudo kill $$(ps aux | grep '[f]irefox' | awk '{print $$2}') 2>/dev/null || true
	sudo pkill flask  --signal SIGINT || true
	sudo pkill python3 --signal SIGINT || true
	sudo pkill pycopy --signal SIGINT || true
	sudo pkill java   --signal SIGINT || true
	make stop-historian
	sudo mn -c
	sleep 3
	make kill-processes
	clear

common: clear
	@# cd historian && make
	if [ ! -e /etc/hosts.bak ]; then \
		sudo cp /etc/hosts /etc/hosts.bak; \
	fi
	if [ -e nft-rules/hosts.conf ]; then \
		sudo cp nft-rules/hosts.conf /etc/hosts; \
	fi

# Delay testing related targets
frequency ?= 1
bandwidth ?= 1000
jitter ?= 0
loss ?= 0
delay ?= 0
nlinks ?= 30
test-delay: common kill-processes
	sudo $(PYTHON) test_delay.py \
		-f $(frequency) -b $(bandwidth) -j $(jitter) \
		-l $(loss) -d $(delay) -n $(nlinks) || echo "Python exited with errors."
	make clean-simulation

# ICS simulator related targets
clean-install:
	echo "Removing directory '$(PYCOPY_BUILD_DIR)'..."
	rm -rf $(PYCOPY_BUILD_DIR)/ || true

pycopy-build: clean-install
	git clone --depth=1 https://github.com/pfalcon/pycopy.git $(PYCOPY_BUILD_DIR)
	echo "Building mpy-cross"
	cd $(PYCOPY_BUILD_DIR)/ && make -C mpy-cross
	make clear

pycopy-build-lib:
	echo "Copying specified standard libraries: $(PYCOPY_STDLIB)"
	git clone --depth=1 https://github.com/GimmickNG/sim-pycopy-lib.git $(PYCOPY_BUILD_DIR)/.pycopy-lib
	git clone https://github.com/GimmickNG/pycopy-modbus.git $(UMODBUS_BUILD_DIR)/.umodbus
	cd $(UMODBUS_BUILD_DIR)/.umodbus && git switch mpmodbus-compatibility && mv umodbus/ ../
	rm -rf $(UMODBUS_BUILD_DIR)/.umodbus
	cd $(PYCOPY_BUILD_DIR)/.pycopy-lib && $(PYTHON) ./install.py $(PYCOPY_STDLIB) ../ports/unix/modules/
	cp -r pycopy-tools/uasyncio $(PYCOPY_BUILD_DIR)/ports/unix/modules/
	cp -r pycopy-tools/umodbus/ $(PYCOPY_BUILD_DIR)/ports/unix/modules/umodbus
	echo "Building Pycopy Unix port..."
	cd $(PYCOPY_BUILD_DIR)/ports/unix && make submodules && make
	if [ -n "$(PYCOPY_LIBS)" ]; then \
		echo "Installing pycopy pip packages prior to freeze"; \
		cd $(PYCOPY_BUILD_DIR)/ports/unix && ./pycopy -m upip install -p ./modules/ $(addprefix pycopy-,$(PYCOPY_LIBS)); \
		echo "Rebuilding with frozen packages"; \
		cd $(PYCOPY_BUILD_DIR)/ports/unix && make clean-frozen && make clean && make; \
	fi

pycopy-install: pycopy-build pycopy-build-lib clear
	cp $(PYCOPY_BUILD_DIR)/ports/unix/pycopy ./
	echo "Installed Pycopy successfully."

pymodbus-install:
	sudo $(PYTHON) -m pip install git+https://github.com/riptideio/pymodbus.git

first-run:
ifeq (,$(wildcard ./pycopy))
	make clear
	echo "Pycopy does not exist. Installing with frozen packages."
	make pycopy-install || echo "Error during installation."
	make clean-install
endif

compile-package: clean-install
	sudo rm -rf ./pycopy ./logs/* ./__pycache__
	sudo rm -rf ./simulator/controlblock/__pycache__
	sudo rm -rf ./simulator/plc/__pycache__
	sudo rm -rf ./simulator/__pycache__
	sudo rm -rf ./simulator/HMI/__pycache__
	sudo rm -rf ./simulator/logicblock/__pycache__
	sudo rm -rf ./simulator/io_plc/__pycache__
	sudo rm -rf ./simulator/modbus/__pycache__
	sudo rm -rf ./simulator/modbus/compat/__pycache__
	sudo rm -rf ./simulator/modbus/types/__pycache__
	sudo rm -rf ./simulator/config/__pycache__
	cd ../ && makeself --notemp $(shell pwd) cyberswat.run "CyberSWaT Self-Extractor" ./install.sh

# requires AWS EC2 ssh key in parent folder (MininetICS.pem)
deploy: compile-package
	scp -i ../MininetICS.pem ../cyberswat.run ubuntu@$(to):
	ssh -i ../MininetICS.pem ubuntu@$(to)
	
kill-processes:
	sudo pkill flask  || true
	sudo pkill python3 || true
	sudo pkill pycopy || true
	sudo pkill java   || true
	
# normal run
run: common first-run kill-processes clear 
	rm -rf ./logs/*
	sudo $(PYTHON) run_simulator.py
	make clean-simulation

## auxiliary targets - used by devices
# setup routers
router-remote: clear
	nft -f nft-rules/rem_r.nft
router-gate: clear
	nft -f nft-rules/gate_r.nft

# hmi (dumb terminal)
historian-viewer:
	sudo -u mininet firefox $(HISTORIAN_URL)

# historian
start-historian:
	@# cd historian && java -jar h2db.jar -url jdbc):h2:mem:historian -tcpAllowOthers
	sudo $(MANGO_DIR)/start-mango.sh
stop-historian:
	sudo $(MANGO_DIR)/stop-mango.sh 2>/dev/null || true

dashboard:
	cd sim-client/ && $(PYTHON) appdash.py
## end

install-desktop:
	sudo apt install -y lxde && sudo reboot

#todo add server url to allow connection via tcp? test on mininet?
$(v).SILENT:
.INTERMEDIATE: kill-processes
