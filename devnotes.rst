===============
Making releases
===============

1. Update version in ``setup.py``.
2. Build, register, upload: ``python setup.py sdist bdist register upload``.
3. Update ``conda/meta.yaml``. Get MD5 from::

     curl -s https://pypi.python.org/pypi/bibtools/ |grep md5= |grep -v linux |sed -e 's/.*md5=//'

4. Build for ``conda``: ``conda build conda``.
5. Upload to ``anaconda.org``: execute line at end of the ``conda build`` output.
