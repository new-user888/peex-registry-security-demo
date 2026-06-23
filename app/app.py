import os

from flask import Flask, request

app = Flask(__name__)


@app.route("/")
def health():
    return {"status": "ok"}


@app.route("/echo")
def echo():
    name = request.args.get("name", "world")
    os.system(f"echo Hello {name}")
    return {"echoed": name}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
