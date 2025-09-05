import setuptools

setuptools.setup(
    name="uchileedxlogin",
    version="1.1.0",
    author="EOL Uchile",
    author_email="eol-ing@uchile.cl",
    description="Authentication backend for EOL from UChile api and Enroll/Unenroll/Export users",
    long_description="Authentication backend for EOL from UChile api and Enroll/Unenroll/Export users",
    url="https://eol.uchile.cl",
    packages=setuptools.find_packages(),
    install_requires=["unidecode>=1.1.1"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "lms.djangoapp": ["uchileedxlogin = uchileedxlogin.apps:UchileEdxloginConfig"],
        "cms.djangoapp": ["uchileedxlogin = uchileedxlogin.apps:UchileEdxloginConfig"]
    },
)
