import os
from syzqemuctl._version import __title__, __version__, __author__, __email__, __description__, __url__
from setuptools import setup, find_packages

REQUIRED = [
    'click',
    'rich',
    'scp',
    'paramiko'
]

here = os.path.abspath(os.path.dirname(__file__))

try:
    with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = '\n' + f.read()
except FileNotFoundError:
    long_description = __description__


setup(
    name=__title__,
    version=__version__,
    description=__description__,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author=__author__,
    author_email=__email__,
    url=__url__,
    packages=find_packages(exclude=['tests', 'tests.*', '*.tests', '*.tests.*']),
    entry_points={
        'console_scripts': [
            'syzqemuctl=syzqemuctl.cli:cli',
        ],
    },
    install_requires=REQUIRED,
    include_package_data=True,
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
