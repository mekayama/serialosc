#!/usr/bin/env python

import subprocess
import time
import sys

top = "."
out = "build"

# change this stuff

APPNAME = "serialosc"
VERSION = "1.4"

#
# dep checking functions
#

def check_poll(conf):
	# borrowed from glib's poll test

	code = """
		#include <stdlib.h>
		#include <poll.h>

		int main(int argc, char **argv) {
		    struct pollfd fds[1];

		    fds[0].fd = open("/dev/null", 1);
		    fds[0].events = POLLIN;

		    if (poll(fds, 1, 0) < 0 || fds[0].revents & POLLNVAL)
		        exit(1);
		    exit(0);
		}"""

	conf.check_cc(
		define_name="HAVE_WORKING_POLL",
		mandatory=False,
		quote=0,

		execute=True,

		fragment=code,

		msg="Checking for working poll()",
		errmsg="no (will use select())")

def check_udev(conf):
	conf.check_cc(
		define_name="HAVE_LIBUDEV",
		mandatory=False,
		quote=0,

		lib="udev",
		uselib_store="UDEV",

		msg="Checking for libudev",
		errmsg="no (will use sysfs)")

def check_liblo(conf):
	conf.check_cc(
		define_name="HAVE_LO",
		mandatory=True,
		quote=0,

		lib="lo",
		uselib_store="LO",

		msg="Checking for liblo")

def check_libmonome(conf):
	conf.check_cc(
		define_name="HAVE_LIBMONOME",
		mandatory=True,
		quote=0,

		lib="monome",
		header_name="monome.h",
		uselib_store="LIBMONOME",

		msg="Checking for libmonome")

def check_strfuncs(ctx):
	check = lambda func_name: ctx.check_cc(
			define_name='HAVE_{}'.format(func_name.upper()),
			mandatory=False,
			quote=0,

			header_name='string.h',
			function_name=func_name)

	check('strdup')
	check('_strdup')
	check('strndup')
	check('strcasecmp')

def check_dnssd_win(conf):
	conf.check_cc(
		mandatory=True,
		header_name="dns_sd.h",
		includes=["c:/program files/bonjour sdk/include"],
		uselib_store="DNSSD_INC")


def check_dnssd(conf):
	conf.check_cc(
		mandatory=True,
		header_name="dns_sd.h")

def check_submodules(conf):
	if not conf.path.find_resource('third-party/libuv/uv.gyp'):
		raise conf.errors.ConfigurationError(
			"Submodules aren't initialized!\n"
			"Make sure you've done `git submodule init && git submodule update`.")

def load_tools(ctx):
	tooldir = ctx.path.find_dir('waftools').abspath()
	load_tool = lambda t: ctx.load(t, tooldir=tooldir)

	load_tool('gyp_wrapper')
	load_tool('winres_gen')

def override_find_program(prefix):
	from waflib.Configure import find_program as orig_find
	from waflib.Configure import conf

	if prefix[-1] != '-':
		prefix += '-'

	@conf
	def find_program(self, filename, **kw):
		if type(filename) == str:
			return orig_find(self, prefix + filename, **kw)
		else:
			return orig_find(self, [prefix + x for x in filename], **kw)
		return orig_find(self, filename, **kw)

#
# waf stuff
#

def options(opt):
	opt.load("compiler_c")

	xcomp_opts = opt.add_option_group('cross-compilation')
	xcomp_opts.add_option('--host', action='store', default=False)

	sosc_opts = opt.add_option_group("serialosc options")
	sosc_opts.add_option("--enable-multilib", action="store_true",
			default=False, help="on Darwin, build serialosc as a combination 32 and 64 bit executable [disabled by default]")
	sosc_opts.add_option("--disable-zeroconf", action="store_true",
			default=False, help="disable all zeroconf code, including runtime loading of the DNSSD library.")

def configure(conf):
	# just for output prettifying
	# print() (as a function) ddoesn't work on python <2.7
	separator = lambda: sys.stdout.write("\n")

	check_submodules(conf)

	if conf.options.host:
		override_find_program(conf.options.host)

	separator()
	conf.load('compiler_c')
	conf.load('gnu_dirs')
	load_tools(conf)

	if conf.env.DEST_OS == "win32":
		conf.load("winres")

		conf.env.append_unique("LIBPATH", conf.env.LIBDIR)
		conf.env.append_unique("CFLAGS", conf.env.CPPPATH_ST % conf.env.INCLUDEDIR)

	if conf.options.host:
		conf.env.append_unique("LIBPATH", conf.env.PREFIX + '/lib')
		conf.env.append_unique("CFLAGS",
				conf.env.CPPPATH_ST % conf.env.PREFIX + '/include')

	#
	# conf checks
	#

	separator()

	if conf.env.DEST_OS != "win32":
		check_poll(conf)

	if conf.env.DEST_OS == "linux":
		check_udev(conf)

	check_libmonome(conf)
	check_liblo(conf)

	# stuff for libconfuse
	check_strfuncs(conf)
	conf.check_cc(define_name='HAVE_UNISTD_H', header_name='unistd.h')

	if conf.env.DEST_OS == "win32":
		if not conf.options.disable_zeroconf:
			check_dnssd_win(conf)
	elif conf.env.DEST_OS != "darwin":
		if not conf.options.disable_zeroconf:
			check_dnssd(conf)
		conf.check_cc(lib='dl', uselib_store='DL', mandatory=True)

	separator()

	#
	# setting defines, etc
	#

	if conf.options.enable_multilib:
		conf.env.ARCH = ["i386", "x86_64"]

	if conf.env.DEST_OS == "win32":
		conf.define("WIN32", 1)
		conf.env.append_unique("LIB_LO", "ws2_32")
		conf.env.append_unique("LINKFLAGS",
				['-static', '-static-libgcc',
					'-Wl,--enable-stdcall-fixup'])
		conf.env.append_unique("WINRCFLAGS", ["-O", "coff"])
	elif conf.env.DEST_OS == "darwin":
		conf.env.append_unique("CFLAGS", ["-mmacosx-version-min=10.5"])
		conf.env.append_unique("LINKFLAGS", ["-mmacosx-version-min=10.5"])

	if conf.options.disable_zeroconf:
		conf.define("SOSC_NO_ZEROCONF", True)
		conf.env.SOSC_NO_ZEROCONF = True

	conf.env.append_unique("CFLAGS", ["-std=c99", "-Wall", "-Werror"])

	conf.env.VERSION = VERSION

	try:
		import os

		devnull = open(os.devnull, 'w')

		conf.env.GIT_COMMIT = subprocess.check_output(
			["git", "rev-parse", "--verify", "--short", "HEAD"],
			stderr=devnull).decode().strip()
	except subprocess.CalledProcessError:
		conf.env.GIT_COMMIT = ''

	conf.define("VERSION", VERSION)
	conf.define("_GNU_SOURCE", 1)
	conf.define("GIT_COMMIT", conf.env.GIT_COMMIT)

	conf.write_config_header("config-autogen.h", remove=False)

def build(bld):
	bld.get_config_header("config-autogen.h")
	bld.recurse("third-party")
	bld.recurse("src")

def dist(dst):
	pats = [".git*", "**/.git*", ".travis.yml", "**/__pycache__"]
	with open(".gitignore") as gitignore:
	    for l in gitignore.readlines():
	        if l[0] == "#":
	            continue

	        pats.append(l.rstrip("\n"))

	dst.excl = " ".join(pats)
