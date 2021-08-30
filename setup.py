from setuptools import setup

setup(name='superfsmon',
      version='1.2.1',
      license='MIT',
      description='Supervisor plugin to watch a directory and restart '
                  'programs on changes',
      author='Tim Schumacher',
      author_email='tim@timakro.de',
      url='https://github.com/timakro/superfsmon',
      install_requires=[
          'supervisor >= 4.0.0     ; sys_platform != "win32"',
          'supervisor-win >= 4.0.0 ; sys_platform == "win32"',
          'watchdog',
      ],
      packages=['superfsmon'],
      entry_points={
          'console_scripts': ['superfsmon=superfsmon:main']
      })
