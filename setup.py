#!/usr/bin/python

from setuptools import setup, find_packages

description = ''.join([x for x in open('README.rst')])

setup(
    name='JSTools',
    version='1.0',
    description="assorted python tools for building (packing, aggregating) javascript libraries",
    long_description=description,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: JavaScript",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: BSD License"
    ],
    keywords='javascript',
    author='assorted',
    author_email='jstools@googlegroups.com',
    url='https://github.com/camptocamp/jstools',
    license='various/BSDish',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    include_package_data=True,
    zip_safe=True,
    entry_points={
        "zc.buildout": [
            "default=jstools.bo:BuildJS",
            "buildjs=jstools.bo:BuildJS",
        ],
        "console_scripts": [
            "jsbuild=jstools.build:build",
            "jsmin=jstools.jsmin:minify",
            "jst=jstools.jst:run",
        ],
        "jstools.jsbuild_command": [
            "default=jstools.build:default_merge",
        ],
        "jstools.compressor": [
            "default=jstools.jsmin:compressor_plugin",
            "yui=jstools.yuicompressor:compress [yuicompressor]",
        ],
        "jstools.docs": [
            "default=jstools.jst [sphinx]",
        ],
        "paste.app_factory": [
            "main=jstools.proxy:make_proxy [proxy]",
        ],
    },
    extras_require=dict(
        yuicompressor=["Paver"],
        sphinx=['Jinja2'],
        proxy=['WSGIProxy']
    ),
    test_suite='nose.collector',
    tests_require=['nose']
)
