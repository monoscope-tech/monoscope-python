from setuptools import setup, find_packages

setup(
    name="monoscope-common",
    version="1.0.0",
    description="Shared code for apitoolkit python sdks",
    author="Yussif Mohammed",
    author_email="yousiph77@gmail.com",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.7",
    install_requires=[
        "opentelemetry-api>=1.0.0",
        "requests>=2.0.0",
        "pytz>=2020.1",
        "jsonpath-ng>=1.5.3",
        "httpx>=0.18.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/monoscope-tech/apitoolkit-python",
)
