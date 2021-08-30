from setuptools import setup

setup(name='superfsmon',
      version='1.2.0',
      license='MIT',
      description='Supervisor plugin to watch a directory and restart '
                  'programs on changes',
      author='Tim Schumacher',
      author_email='tim@timakro.de',
      url='https://github.com/timakro/superfsmon',
      install_requires=['supervisor', 'watchdog'],
      packages=['superfsmon'],
      entry_points={
          'console_scripts': ['superfsmon=superfsmon:main']
      })
