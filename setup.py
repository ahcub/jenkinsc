from distutils.core import setup

from setuptools import find_packages

with open('README.md') as file:
    long_description = file.read()


setup(
    name='jenkinsc',
    packages=find_packages(include=('jenkinsc', )),
    version='0.0.33',
    description='bulletproof jenkins client',
    author='Alex Buchkovsky',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author_email='olex.buchkovsky@gmail.com',
    url='https://github.com/ahcub/jenkinsc',
    keywords=['jenkins', 'automation', 'ci', 'client', 'python'],
)
