from setuptools import setup

setup(name='superfsmon',
      version='1.1.1',
      license='GPLv3',
      description='Supervisor plugin to watch a directory and restart '
                  'programs on changes',
      author='Tim Schumacher',
      author_email='tim@timakro.de',
      url='https://github.com/timakro/superfsmon',
      install_requires=['supervisor', 'watchdog'],
      scripts=['superfsmon']
      )
