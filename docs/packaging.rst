PyPI readiness
==============

Assessment
----------

Wappler is close to a small initial Python package release. It already has
PEP 517 build metadata, a GPLv3 license, a src layout, runtime dependencies,
optional development dependencies, a Markdown project description, and a
module entry point. PyPI distributes the code; it does not run the service.

A public lookup of the wappler project on 2026-10-03 returned HTTP 404.
This does not reserve the name or prove PyPI will accept it: name restrictions,
ownership and confusingly similar projects still need review at publication.

Build and metadata checks
-------------------------

From the checkout::

   uv run --frozen --extra dev python -m build
   uv run --frozen --extra dev --with twine python -m twine check --strict dist/*

The wheel should include the wappler package and license. The source distribution
also includes documentation and the two audio fixtures used by tests. Review
permission to redistribute the recorded voice before a public upload.

Neither archive should contain .env, captured webhooks, local environment
directories, or generated documentation. Inspect contents after building.
Use absolute repository/image links in the README so they remain useful on
a package index page.

Installed-package use
---------------------

Install a locally built wheel before publishing::

   python -m pip install dist/wappler-0.0.1-py3-none-any.whl
   python -m uvicorn wappler.api:wappler_app --env-file /path/to/private.env --port 8000

Run those commands in a fresh environment. The application requires the same
credentials and allowlist as a source checkout. Automatic .env discovery
currently assumes the src checkout; explicit environment injection avoids that
assumption after installation.

The optional python -m wappler.run entry point also works with environment
variables and respects PORT. A shorter console command and an explicit config
file option would improve usability but are not PyPI requirements.

Release checklist
-----------------

1. Review the public project name, version, description, license and voice-fixture
   redistribution. Check name ownership and potential confusion with similarly
   named projects before establishing a public package identity.
2. Run offline tests, dependency audit, Sphinx and a clean distribution build.
3. Inspect wheel/source contents and check their metadata with Twine.
4. Install the wheel in an isolated environment and verify imports and app startup.
5. Publish to TestPyPI and check the package page plus an install from that index.
   PyPI and TestPyPI are separate services; a local build is not an index upload.
6. Add a tagged-release workflow with an approved publishing environment. Prefer
   PyPI Trusted Publishing with short-lived OIDC credentials and id-token: write
   restricted to the publish job.
7. Upload the same verified artifacts to PyPI and document version changes.

No package has been uploaded and no publishing workflow or publisher identity
has been configured by this review.

Two different readiness questions
---------------------------------

Package readiness is mostly metadata, installability and release automation.
Production-service readiness still includes hosted acceptance, recovery and
delivery monitoring. Jobs, duplicate protection and quotas now exist, but
publishing a wheel does not verify their deployment. Earlier MIT metadata was
incorrect: LICENSE contains GPLv3. Review licensing intent before publishing.

References
----------

* `Python packaging tutorial <https://packaging.python.org/en/latest/tutorials/packaging-projects/>`_
* `PyPI Trusted Publishing <https://docs.pypi.org/trusted-publishers/>`_
