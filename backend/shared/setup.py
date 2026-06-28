from setuptools import setup, find_packages

setup(
    name="vcd_shared",
    version="0.1.0",
    description="Shared Pydantic schemas, exceptions and logging for VietCropDoctor services",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pydantic>=2.0.0",
        "aiokafka>=0.10.0",
        # Auth
        "python-jose[cryptography]>=3.3.0",
        "passlib[bcrypt]>=1.7.4",
        # Rate limiting / API keys
        "redis[hiredis]>=5.0.0",
    ],
)
