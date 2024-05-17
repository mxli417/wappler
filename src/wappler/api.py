from pprint import pprint
from typing import Union

import soundfile as sf
from fastapi import FastAPI
from pydantic import BaseModel

from wappler.stats.watchmen import LightWatch
from wappler.utils import config
from wappler.utils.log import get_logger

logger = get_logger(__name__)

# TODO: pydantic request data model


app = FastAPI()
tracker = LightWatch()


@app.get("/", methods=["GET"])
def home():
    return "OK", 200


@app.get("/heartbeat", methods=["GET"])
def liveness():
    # TODO: look up and reset to kubernetes status call routes
    return "OK", 200


@app.get("/stats", methods=["GET"])
def liveness():
    return {"Throughput": tracker.report}, 200


@app.post("/v0/twilio", methods=["POST"])
def speech2text(req: Request):
    try:
        data = req.form.todict()
        pprint(data)
        # TODO: activate ngrok+twilio and try to make this work
        # TODO: further data handling
        # TODO: throughput stats tracking
        # TODO: exception and error handling
        # TODO: security filtering to only allow twilio in production
    except Exception as e:
        logger.error("Encountered exception: %s" % e)
        return "Internal Server Error", 500
    else:
        # TODO: send message back to twilio
        # TODO: then maybe replace the 200 code
        return "OK", 200

    # TODO: get media url from twilio here via incoming whatsapp testing
    # TODO: return a text representation
    # TODO: post back to twilio endpoint
    # TODO: test with Postman


# TODO: main todo before prod - secure the communication, s.t. only authorized
# (twilio) accounts can call the transcription service
