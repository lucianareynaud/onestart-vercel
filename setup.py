from setuptools import setup, find_packages

setup(
    name="linkedin_scraper",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "scrapy>=2.8.0",
        "scrapy-rotating-proxies>=0.6.2",
        "apache-airflow>=2.6.3",
        "transformers>=4.31.0",
        "torch>=2.0.1",
        "python-dotenv>=1.0.0",
        "SQLAlchemy>=2.0.17",
        "psycopg2-binary>=2.9.6",
        "httpx>=0.24.1",
        "beautifulsoup4>=4.12.2",
    ],
    python_requires=">=3.11",
    author="AI Engineer",
    author_email="ai@example.com",
    description="LinkedIn profile scraper for sales lead generation",
    keywords="linkedin, scraping, sales, leads",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Sales Teams",
        "Programming Language :: Python :: 3.11",
        "Topic :: Internet :: WWW/HTTP :: Indexing/Search",
    ],
) 