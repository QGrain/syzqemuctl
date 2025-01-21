import os
import ast
# from syzqemuctl._version import __title__, __version__, __author__, __email__, __description__, __url__
from setuptools import setup, find_packages

def read_version_info(filename):
    with open(filename) as f:
        tree = ast.parse(f.read())
    
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name.startswith('__') and name.endswith('__'):
                    result[name] = ast.literal_eval(node.value)
    return result

info = read_version_info("syzqemuctl/_version.py")

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
    long_description = info["__description__"]


setup(
    name=info["__title__"],
    version=info["__version__"],
    description=info["__description__"],
    long_description=long_description,
    long_description_content_type='text/markdown',
    author=info["__author__"],
    author_email=info["__email__"],
    url=info["__url__"],
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
