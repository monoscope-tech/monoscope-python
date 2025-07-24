from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="monoscope-django",
    version='1.0.1',
    packages=find_packages(),
    description='A Django SDK for Monoscope integration',
    long_description=long_description,
    long_description_content_type="text/markdown",
    author_email='hello@apitoolkit.io',
    author='monoscope',
    install_requires=[
        'Django',
        'monoscope-common',
        "opentelemetry-api>=1.0.0",
    ]
)
