from setuptools import setup, find_packages
import os

setup(
    name='simple-cpu',
    version='0.5',
    author='Kevin Veroneau',
    author_email='kveroneau@gmail.com',
    description='A Simple CPU/Virtual Machine and Assembler.',
    long_description=open(os.path.join(os.path.dirname(__file__), 'README.md')).read(),
    scripts=['simple_cpu/bin/cpu.py', 'simple_cpu/bin/asm.py'],
    entry_points={'console_scripts': [
        'cpu = simple_cpu.cpu:main',
        'asm = simple_cpu.asm:main',
    ]},
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: LGPL License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
    license='LGPL',
    keywords='cpu simulator virtual machine assembler',
    url='https://bitbucket.org/kveroneau/simple-cpu',
    packages=find_packages(),
    zip_safe=False,
)
