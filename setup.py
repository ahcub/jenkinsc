from distutils.core import setup

from setuptools import find_packages

setup(
    name='jenkinsc',
    packages=find_packages(include=('jenkinsc', )),
    version='0.0.10',
    description='bulletproof jenkins client',
    author='Alex Buchkovsky',
    author_email='olex.buchkovsky@gmail.com',
    url='https://github.com/ahcub/jenkinsc',
    keywords=['jenkins', 'automation', 'ci', 'client', 'python'],
)
