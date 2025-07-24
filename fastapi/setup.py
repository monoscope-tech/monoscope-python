from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="monoscope-fastapi",
    version="1.0.0",
    packages=find_packages(),
    long_description=long_description,
    long_description_content_type="text/markdown",
    author_email='hello@apitoolkit.io',
    author='Monoscope',
    install_requires=[
        'fastapi',
        'monoscope-common',
        "opentelemetry-api>=1.0.0",
    ]
)
