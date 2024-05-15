from typing import Union

from fastapi import FastAPI

from wappler.utils import config

app = FastAPI()


@app.get("/", methods=["GET", "POST"])
def home():
    return "OK", 200


@app.get("/", methods=["GET", "POST"])
def liveness():
    # TODO: look up and reset to kubernetes status call routes
    return "OK", 200


@app.get("/v0/twilio", methods=["POST"])
def speech2text():
    pass
    # TODO: get media url from twilio here via incoming whatsapp testing
    # TODO: return a text representation
    # TODO: post back to twilio endpoint
    # TODO: test with Postman


# TODO: main todo - secure the communication, s.t. only authorized (twilio) accounts can call the transcription service
