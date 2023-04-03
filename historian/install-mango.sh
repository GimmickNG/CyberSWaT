git clone https://github.com/MangoAutomation/ma-core-public.git mango/
cd mango && git checkout 4.3.x
cd Core/bin/ && chmod +x *.sh
sudo apt install maven
mvn package

# TODO: automated install
# currently, must be installed manually