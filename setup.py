import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="climar-seas-prob-forec-marisolosman",
    version="0.0.1",
    author="Marisol Osman",
    author_email="osman@cima.fcen.uba.ar",
    description="Package to run seasonal prob forecast",
    long_description="Calibration and combination of NMME temperature and precipitation "
                     "forecast through ensemble regression",
    long_description_content_type="text/markdown",
    url="https://github.com/marisolosman/ereg_calibracion_combinacion",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Licence :: GNU GPLv3"
    ],
    python_requires='=3.7',
)


