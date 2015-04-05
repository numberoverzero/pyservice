from setuptools import setup, find_packages


setup(
    name='pyservice',
    version='0.8.0',
    description='web services with python made easy',
    long_description=open('README.md').read(),
    author='Joe Cross',
    author_email='joe.mcross@gmail.com',
    url='http://github.com/numberoverzero/pyservice/',
    packages=find_packages(exclude=('tests', 'examples')),
    install_requires=['requests', 'ujson'],
    license='MIT',
    platforms='any',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Server',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords='wsgi web api framework soa'
)
