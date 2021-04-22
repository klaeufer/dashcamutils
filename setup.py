# -*- coding: utf-8 -*-

# Learn more: https://github.com/kennethreitz/setup.py

from setuptools import setup, find_packages

with open('README.md') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

setup(
    name='dashcamutils',
    version='0.1.0',
    description='Garmin Dash Cam utilities for populating EXIF metadata from visual timestamp embedded in images',
    long_description=readme,
    author='Konstantin Läufer',
    author_email='laufer@cs.luc.edu',
    url='https://github.com/klaeufer/dashcamutils',
    license=license,
    packages=find_packages(exclude=('tests', 'docs'))
)
