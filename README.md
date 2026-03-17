# IMPORTANT

This project uses python v3.12.3

before beginning development, run:

pip install -r requirements.txt

If you added a new package, run

pip freezez > requirements.txt

You should create a venv to avoid dependency conflicts, and to avoid needing pymongo package on a sql project

To create a new venv:
1. python -m venv /path/to/new/venv
2. source /path/to/new/venv/bin/activate