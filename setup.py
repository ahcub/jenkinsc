from distutils.core import setup

from setuptools import find_packages

with open('README.txt') as file:
    long_description = file.read()


setup(
    name='jenkinsc',
    packages=find_packages(include=('jenkinsc', )),
    version='0.0.28',
    description='bulletproof jenkins client',
    author='Alex Buchkovsky',
    long_description=long_description,
    author_email='olex.buchkovsky@gmail.com',
    url='https://github.com/ahcub/jenkinsc',
    keywords=['jenkins', 'automation', 'ci', 'client', 'python'],
)
