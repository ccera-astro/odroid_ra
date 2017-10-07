BINFILES=corrint_uhd.py psr_sender.py ra_detector_receiver.py rsu.py \
  ra_pulsar_receiver.py ra_sender.py run_odroid start_pulsars fake_pulsar.py \
  led_cal_controller.py methanol_sender.py ra_adding_double.py \
  psycho_killer.py
SRCFILES=corrint_uhd.grc psr_sender.grc ra_sender.grc methanol_sender.grc ra_adding_double.grc
FILES=$(BINFILES) $(LIBFILES) $(SRCFILES)
install: $(FILES)
	cp $(BINFILES) /usr/local/bin
	chmod 755 /usr/local/bin/*
	mkdir -p /usr/local/src
	cp $(SRCFILES) /usr/local/src
tarfile: $(FILES)
	tar cvzf odroid_ra.tar.gz $(FILES) Makefile
