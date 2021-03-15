from setuptools import find_packages, setup

setup(
    name='fake_swift',
    version='0.0.1',
    description='Fake Swift',
    author='Storm',
    author_email='storm@g.globo',
    install_requires=[
        'Flask==1.1.2',
        'PasteDeploy==2.1.1',
        'keystonemiddleware==9.2.0'
    ],
    packages=find_packages(),
    include_package_data=True,
)
