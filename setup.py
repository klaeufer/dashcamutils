# -*- coding: utf-8 -*-

# Learn more: https://github.com/kennethreitz/setup.py

from setuptools import setup, find_packages
from dashcamutils import version

with open('README.md') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

with open('requirements.txt') as f:
    requirements = [line.rstrip() for line in f]

setup(
    name='dashcamutils',
#    version=dashcamutils.version(),
    version=version.version(),
    description='Garmin Dash Cam utilities for populating EXIF metadata from visual timestamp embedded in images',
    long_description=readme,
    author='Konstantin Läufer',
    author_email='laufer@cs.luc.edu',
    url='https://github.com/klaeufer/dashcamutils',
    license=license,
    python_requires='>=3',
    install_requires=requirements,
    packages=find_packages(exclude=('tests', 'docs')),
    entry_points = {
        'console_scripts': [
            'tag_images = dashcamutils.tag_images:main'
        ]
    }
)
