"""Compatibility entrypoint for platforms still configured to run `python server.py`."""

import os

import uvicorn

from main_app import app


if __name__ == '__main__':
    port = int(os.getenv('PORT', '8080'))
    uvicorn.run(app, host='0.0.0.0', port=port)
