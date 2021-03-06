CubETL
======

CubETL is a *lightweight* tool for data ETL (Extract, Transform and Load).

Features:

* SQL support
* Consumes and produces CSV, XML, JSON...
* Support for templating, GeoIP, network queries
* OLAP support:
  * Star-schema generation and transparent data loading
  * Cubes OLAP Server model export
* Common types library (dates, geo...)
* Modular and extensible
* Flexible configuration via YAML
* Caching

Usage
-----

For installation instructions, see "Download / Install" below.


Download / Install
------------------




Documentation
=============

* Quick Start

* Usage
  * Introduction
  * Running CubETL
  * Configuration files
  * Expressions (message, context, ternary operator...)
  * Process flow
* Component Reference

* Notes to be included:

Running from Python
-------------------

In order to configure and/or run a process from client code, use:

    from cubetl.core.bootstrap import Bootstrap

    # Create Cubetl context
    bootstrap = Bootstrap()
    ctx = bootstrap.init()
    ctx.debug = True

    # Extra configuration

    # Add components ...
    comp = ...
    cubetl.container.add_component(comp)

    # Launch process
    ctx.start_node = "your_app.node_id"
    result = bootstrap.run(ctx)



Support
=======

If you have questions, problems or suggestions, please use:

* Report bugs: https://github.com/jjmontesl/cubetl/issues

If you are using or trying CubETL, please tweet #cubetl.

Source
======

Github source repository: https://github.com/jjmontesl/cubetl

Authors
=======

CubETL is written and maintained by Jose Juan Montes.

See AUTHORS file for more information.

License
=======

CubETL is published under MIT license.

For full license see the LICENSE file.

Other sources:

* Country list from: http://www.geonames.org (CC-A 3.0)

