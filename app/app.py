import subprocess

from flask import Flask, request
from markupsafe import escape

app = Flask(__name__)


@app.route("/")
def health():
    return {"status": "ok"}


@app.route("/echo")
def echo():
    name = request.args.get("name", "world")
    # fixed: py/command-line-injection - no shell, args passed as a list
    subprocess.run(["echo", "Hello", name], shell=False, check=False)
    # fixed: py/reflective-xss - escape before reflecting user input back
    return {"echoed": str(escape(name))}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
