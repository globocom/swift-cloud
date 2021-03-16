from setuptools import find_packages, setup

setup(
    name='swift_gcp',
    version='0.0.1',
    description='Middleware for Swift to store objecs on GCP',
    author='Storm',
    author_email='storm@g.globo',
    install_requires=[
        'WebOb==1.8.7'
    ],
    packages=find_packages(),
    include_package_data=True,
)
