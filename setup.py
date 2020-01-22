import setuptools

setuptools.setup(
    name="uchileedxlogin",
    version="0.0.1",
    author="Felipe Espinoza",
    author_email="felipe.espinoza.r@uchile.cl",
    description="Authentication backend for Chile uchileedxlogin",
    long_description="Authentication backend for Chile uchileedxlogin",
    url="https://eol.uchile.cl",
    packages=setuptools.find_packages(),
    install_requires=["text-unidecode>=1.2"],
    classifiers=[
        "Programming Language :: Python :: 2",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={"lms.djangoapp": ["uchileedxlogin = uchileedxlogin.apps:EdxloginConfig"]},
)
