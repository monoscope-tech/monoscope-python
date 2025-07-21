<div align="center">

![Monoscope's Logo](https://github.com/monoscope-tech/.github/blob/main/images/logo-white.svg?raw=true#gh-dark-mode-only)
![Monoscope's Logo](https://github.com/monoscope-tech/.github/blob/main/images/logo-black.svg?raw=true#gh-light-mode-only)

## Flask SDK

[![Monoscope SDK](https://img.shields.io/badge/Monoscope-SDK-0068ff?logo=flask)](https://github.com/topics/monoscope-sdk) [![PyPI - Version](https://img.shields.io/pypi/v/monoscope-flask)](https://pypi.org/project/monoscope-flask) [![PyPI - Downloads](https://img.shields.io/pypi/dw/monoscope-flask)](https://pypi.org/project/monoscope-flask) [![Join Discord Server](https://img.shields.io/badge/Chat-Discord-7289da)](https://apitoolkit.io/discord?utm_campaign=devrel&utm_medium=github&utm_source=sdks_readme) [![Monoscope Docs](https://img.shields.io/badge/Read-Docs-0068ff)](https://apitoolkit.io/docs/sdks/python/flask?utm_campaign=devrel&utm_medium=github&utm_source=sdks_readme)

APIToolkit Flask SDK is a middleware that can be used to monitor HTTP requests, report errors and monitor outgoing requests. It is provides additional functionalities on top of the open telemetry instrumentation which creates a custom span for each request capturing details about the request including request, response bodies, headers, and more.

</div>

---

## Table of Contents

- [Installation](#installation)
- [Setup Open Telemetry](#setup-open-telemetry)
- [Configuration](#apitoolkit-django-configuration)
- [Contributing and Help](#contributing-and-help)
- [License](#license)

---

## Installation

Kindly run the command below to install the apitoolkit django sdks and necessary opentelemetry packages:

```sh
pip install monoscope-flask opentelemetry-distro opentelemetry-exporter-otlp
opentelemetry-bootstrap -a install
```

## Setup Open Telemetry

Setting up open telemetry allows you to send traces, metrics and logs to the APIToolkit platform.
To setup open telemetry, you need to configure the following environment variables:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otelcol.apitoolkit.io:4317"
export OTEL_SERVICE_NAME="my-service" # Specifies the name of the service.
export OTEL_RESOURCE_ATTRIBUTES="at-project-key={ENTER_YOUR_API_KEY_HERE}" # Adds your API KEY to the resource.
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc" #Specifies the protocol to use for the OpenTelemetry exporter.
```

Then run the command below to start your server with opentelemetry instrumented:

```sh
opentelemetry-instrument flask run --app app
```

## Monoscope Django Configuration

After setting up open telemetry, you can now configure the apitoolkit django middleware.
Next, initialize Monoscope in your application's entry point (e.g., `main.py`), like so:

```python
from flask import Flask
from monoscope_flask import Monoscope

app = Flask(__name__)

# Initialize Monoscope
monoscope = Monoscope(
    service_name = "my-service",
    capture_request_body = True,
    capture_response_body = True,
)

@app.before_request
def before_request():
    monoscope.beforeRequest()

@app.after_request
def after_request(response):
    monoscope .afterRequest(response)
    return response
# END Initialize Monoscope

@app.route('/hello', methods=['GET', 'POST'])
def sample_route():
    return {"Hello": "World"}

app.run(debug=True)
```

> [!NOTE]
>
> The `{ENTER_YOUR_API_KEY_HERE}` demo string should be replaced with the [API key](https://apitoolkit.io/docs/dashboard/settings-pages/api-keys?utm_campaign=devrel&utm_medium=github&utm_source=sdks_readme) generated from the Monoscope dashboard.

<br />

> [!IMPORTANT]
>
> To learn more configuration options (redacting fields, error reporting, outgoing requests, etc.), please read this [SDK documentation](https://apitoolkit.io/docs/sdks/python/flask?utm_campaign=devrel&utm_medium=github&utm_source=sdks_readme).

## Contributing and Help

To contribute to the development of this SDK or request help from the community and our team, kindly do any of the following:

- Read our [Contributors Guide](https://github.com/monoscope-tech/.github/blob/main/CONTRIBUTING.md).
- Join our community [Discord Server](https://apitoolkit.io/discord?utm_campaign=devrel&utm_medium=github&utm_source=sdks_readme).
- Create a [new issue](https://github.com/monoscope-tech/monoscope-flask/issues/new/choose) in this repository.

## License

This repository is published under the [MIT](LICENSE) license.

---

<div align="center">

<a href="https://apitoolkit.io?utm_campaign=devrel&utm_medium=github&utm_source=sdks_readme" target="_blank" rel="noopener noreferrer"><img src="https://github.com/monoscope-tech/.github/blob/main/images/icon.png?raw=true" width="40" /></a>

</div>
