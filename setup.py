from setuptools import setup, find_packages

setup(
    name='music-dsl',
    version='2.0.1',
    description='Program your own music!',
    packages=find_packages(),
    include_package_data=True,
    install_requires=['numpy'],
    entry_points={
        'console_scripts': ['music=music.cli:main'],
    },
)
