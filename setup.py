from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="erpnext_ai_bots",
    version="1.1.0",
    description="AI-powered assistant for ERPNext — chat with your ERP in plain English",
    author="Ludovic Micinthe",
    author_email="dovik@micinthe.com",
    url="https://github.com/byt3crafter/erpnext_ai_bots",
    license="MIT",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
