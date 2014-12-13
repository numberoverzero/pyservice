# pyservice 0.8.0

[![Build Status]
(https://travis-ci.org/numberoverzero/pyservice.svg?branch=master)]
(https://travis-ci.org/numberoverzero/pyservice)[![Coverage Status]
(https://coveralls.io/repos/numberoverzero/pyservice/badge.png?branch=master)]
(https://coveralls.io/r/numberoverzero/pyservice?branch=master)

Downloads https://pypi.python.org/pypi/pyservice

Source https://github.com/numberoverzero/pyservice

Microservice framework for high tps, designed for readability and code re-use

# Installation

`pip install pyservice`

# Getting Started

pyservice was designed from the ground up to minimize request overhead, while
still exposing the relevant pieces of the request chain for extension.  The
file is less than 1000 lines including docstrings and comments
(566 @ 12/12/14), which makes the source a great reference when you've got
questions.

Let's get some code going.  First, we'll define a small api.  These are just
nested dictonaries - feel free to load them from a json file.

```python
# Service/Client just use a dict for specifying an api
api = {
    "debug": True,
    "endpoint": {
        "scheme": "http",
        "host": "localhost",
        "port": 8080,
        "path": "/api/{version}/{operation}"
    },
    "operations": ["get_item", "put_item"],
    "exceptions": ["IDRequired", "DoesNotExist", "ItemRequired"]
}
```

Next we'll set up the service, and define the get/put operations:

```python
import uuid
import pyservice

service = pyservice.Service(**api)
items = {}


@service.operation(name="put_item")
def put_item(request, response, context):
    if item not in request:
        raise service.exceptions.ItemRequired("Need an item to put")
    id = uuid.uuid4()
    items[id] = request.item
    response.id = id


@service.operation(name="get_item")
def get_item(request, response, context):
    if id not in request:
        raise service.exceptions.IDRequired("Can't get an item without an ID")
    try:
        item = items[request.id]
    except KeyError:
        raise service.exceptions.DoesNotExist("No item with id " + response.id)
    else:
        response.item = item
```

Finally, to get a server running, we'll use the wsgiref reference server:

```python
from wsgiref.simple_server import make_server

def run_server():
    print("Starting Server...")
    host, port = api["endpoint"]["host"], api["endpoint"]["port"]
    httpd = make_server(host, port, service.wsgi_application)
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
```

To make a call from a client, we'll use the same `api` defined above.  The
client calls are even simpler:

```python
import pyservice

# ... Same api definition above

client = pyservice.Client(**api)

# put
item = "some string"
id = client.put_item(item=item)

# get
same_item = client.get_item(id=id)

assert item == same_item
```

We can plug into calls in two scopes:

* `request`, which is before the request and response bodies
   have been created and after they've been consumed
* `operation`, which is after the request and response bodies
   have been created and before they've been consumed.

The difference is important for things like sqlalchemy, where serialization
should occur before the connection is closed.

```python

@service.plugin(scope="request")
def some_plugin(context):
    print("Before request '{}'".format(context.operation))
    context.process_request()
    print("After request '{}'".format(context.operation))

@service.plugin(scope="operation")
def some_plugin(request, response, context):
    print("Before operation '{}'".format(context.operation))
    print("Request: {}".format(request))
    context.process_request()
    print("Response: {}".format(response))
    print("After operation '{}'".format(context.operation))
```

# Contributing
Contributions welcome!  Please make sure `tox` passes (including flake8) before submitting a PR.

### Development
pyservice uses `tox`, `pytest` and `flake8`.  To get everything set up:

```
# RECOMMENDED: create a virtualenv with:
#     mkvirtualenv pyservice
git clone https://github.com/numberoverzero/pyservice.git
pip install tox
tox
```

### TODO
* Documentation (0.9.0)
  * Better README
  * Better docstrings
  * Examples
    * Plugins
    * Additional metadata
    * Subclassing Client/Service
    * Multiple versions
* Plugins (1.0.0)
  * Caching
  * Auth[N/Z] + Whitelisting
  * Logging
  * Throttling
  * SqlAlchemy
  * Structures
  * Redaction
  * Patching
  * Function unpacking decoration

# API

### Client

TODO

### Service

TODO

### Plugins

TODO
