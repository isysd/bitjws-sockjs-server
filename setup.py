from setuptools import setup

readme = open('./README.rst').read()

classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 2",
    "Topic :: Software Development :: Libraries"
]

url = 'https://github.com/deginner/bitjws-sockjs-server'

setup(
    name="bitjws-sockjs-server",
    version="0.1.0",
    description="Sockjs to interface message subscriptions using BitJWS",
    long_description=readme,
    author="deginner",
    author_email="support@deginner.com",
    url=url,
    license="MIT",
    classifiers=classifiers,
    include_package_data=True,
    tests_require=["bravado_bitjws"],
    install_requires=[
        "pika",
        "tornado==3.2",
        "sockjs-tornado",
        "websocket-client==0.11.0",
        "bitjws"
    ]
)
