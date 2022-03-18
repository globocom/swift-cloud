from setuptools import find_packages, setup

setup(
    name='swift_cloud',
    version='0.2.15',
    description='Middleware for Openstack Swift to store objecs on multiple cloud providers',
    author='Storm',
    author_email='storm@g.globo',
    install_requires=[
        'swift==2.22.0',
        'google-cloud-storage==1.36.2',
        'requests'
    ],
    packages=find_packages(),
    include_package_data=True,
)
