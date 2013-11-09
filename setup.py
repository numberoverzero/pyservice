from __future__ import print_function
from setuptools import setup
from setuptools.command.test import test as TestCommand
import io
import os
import sys

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
version = '0.0.1'

class Tox(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import tox
        errcode = tox.cmdline(self.test_args)
        sys.exit(errcode)

setup(
    name='pyservice',
    version=version,
    url='http://github.com/numberoverzero/pyservice/',
    license='MIT',
    author='Joe Cross',
    tests_require=['pytest', 'tox'],
    install_requires=['bottle', 'six'],
    cmdclass={'test': Tox},
    author_email='joe.mcross@gmail.com',
    description='web services with python made easy',
    long_description=long_description,
    py_modules=['pyservice'],
    include_package_data=True,
    platforms='any',
    test_suite='pyservice.test',
)
