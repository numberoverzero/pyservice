from __future__ import print_function
from setuptools import setup
import io
import os

here = os.path.abspath(os.path.dirname(__file__))


def read(*filenames, **kwargs):
    encoding = kwargs.get('encoding', 'utf-8')
    sep = kwargs.get('sep', '\n')
    buf = []
    for filename in filenames:
        with io.open(filename, encoding=encoding) as f:
            buf.append(f.read())
    return sep.join(buf)

long_description = read('README')
version = '0.9.0'

setup(
    name='pyservice',
    version=version,
    url='http://github.com/numberoverzero/pyservice/',
    license='MIT',
    author='Joe Cross',
    install_requires=['requests', 'ujson'],
    author_email='joe.mcross@gmail.com',
    description='web services with python made easy',
    long_description=long_description,
    packages=['pyservice'],
    include_package_data=True,
    platforms='any',
    test_suite='pyservice.test',
)
