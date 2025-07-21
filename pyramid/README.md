<div align="center">

![Monoscope's Logo](https://github.com/monoscope-tech/.github/blob/main/images/logo-white.svg?raw=true#gh-dark-mode-only)
![Monoscope's Logo](https://github.com/monoscope-tech/.github/blob/main/images/logo-black.svg?raw=true#gh-light-mode-only)

## Pyramid SDK

[![Monoscope SDK](https://img.shields.io/badge/Monoscope-SDK-0068ff?logo=pyramid)](https://github.com/topics/monoscope-sdk) [![PyPI - Version](https://img.shields.io/pypi/v/monoscope-pyramid)](https://pypi.org/project/monoscope-pyramid) [![PyPI - Downloads](https://img.shields.io/pypi/dw/monoscope-pyramid)](https://pypi.org/project/monoscope-pyramid) [![Join Discord Server](https://img.shields.io/badge/Chat-Discord-7289da)](https://apitoolkit.io/discord?utm_campaign=devrel&utm_medium=github&utm_source=sdks_readme) [![Monoscope Docs](https://img.shields.io/badge/Read-Docs-0068ff)](https://apitoolkit.io/docs/sdks/python/pyramid?utm_campaign=devrel&utm_medium=github&utm_source=sdks_readme)

Monoscope pyramid SDK is a middleware that can be used to monitor incoming HTTP requests, errors and outgoing requests. It is provides additional functionalities on top of the open telemetry instrumentation which creates a custom span for each request capturing details about the request including request, response bodies, headers, status code, duration, etc.

</div>

---

## Table of Contents

- [Installation](#installation)
- [Setup Open Telemetry](#setup-open-telemetry)
- [Configuration](#monoscope-pyramid-configuration)
- [Contributing and Help](#contributing-and-help)
- [License](#license)

---

## Installation

Kindly run the command below to install the apitoolkit pyramid sdks and necessary opentelemetry packages:

```sh
pip install monoscope-pyramid opentelemetry-distro opentelemetry-exporter-otlp

opentelemetry-bootstrap -a install
```

## Setup Open Telemetry

Setting up open telemetry allows you to send traces, metrics and logs to the Monoscope platform.
To setup open telemetry, you need to configure the following environment variables:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otelcol.apitoolkit.io:4317"
export OTEL_SERVICE_NAME="my-service" # Specifies the name of the service.
export OTEL_RESOURCE_ATTRIBUTES="at-project-key={ENTER_YOUR_API_KEY_HERE}" # Adds your API KEY to the resource.
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc" #Specifies the protocol to use for the OpenTelemetry exporter.
```

Then run the command below to start your server with opentelemetry instrumented:

```sh
opentelemetry-instrument python3 myapp.py
```

## Monoscope Pyramid Configuration

After setting up open telemetry, you can now configure and start the apitoolkit pyramid middleware.

```python
from wsgiref.simple_server import make_server
from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.view import view_config


@view_config(
    route_name='home'
)
def home(request):
    return Response('Welcome!')

if __name__ == '__main__':
    setting = {
      "MONOSCOPE_SERVICE_NAME": "my-service",
      "MONOSCOPE_CAPTURE_REQUEST_BODY": True,
      "MONOSCOPE_CAPTURE_RESPONSE_BODY": True
      }
    with Configurator(settings=setting) as config:
        # Initialize Monoscope
        config.add_tween("monoscope_pyramid.Monoscope")
        config.add_route('home', '/')
        config.scan()
        app = config.make_wsgi_app()
    server = make_server('0.0.0.0', 6543, app)
    server.serve_forever()
```
