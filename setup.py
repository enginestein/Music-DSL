from setuptools import setup, find_packages

setup(
    name='music-dsl',
    version='1.0.0',
    description='Program your own music — A simple music DSL',
    packages=find_packages(),
    include_package_data=True,
    install_requires=['numpy'],
    entry_points={
        'console_scripts': ['music=music.cli:main'],
    },
)
