from setuptools import find_packages, setup

setup(
    name='swift_cloud',
    version='0.0.1',
    description='Middleware for Openstack Swift to store objecs on multiple cloud providers',
    author='Storm',
    author_email='storm@g.globo',
    install_requires=[
        'WebOb==1.8.7',
        'google-cloud-storage==1.36.2'
    ],
    packages=find_packages(),
    include_package_data=True,
)
