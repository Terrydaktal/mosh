EXTRA_DIST = wrap-compiler-for-flag-check mosh.pl
if BUILD_CLIENT
  bin_SCRIPTS = mosh-native
endif
CLEANFILES = $(bin_SCRIPTS)

mosh-native:	mosh.pl ../VERSION Makefile
	perl -Mdiagnostics -c $(srcdir)/mosh.pl
	@sed -e "s/\@VERSION\@/`cat ../VERSION`/" -e "s/\@PACKAGE_STRING\@/@PACKAGE_STRING@/" $(srcdir)/mosh.pl > mosh-native
	@chmod a+x mosh-native
