import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_SID = os.getenv("TWILIO_SID")

TWILIO_TEST_MSG_FROM = os.getenv("TWILIO_TEST_MSG_FROM")
TWILIO_TEST_MSG_TO = os.getenv("TWILIO_TEST_MSG_TO")
ENVIRONMENT = os.getenv("ENVIRONMENT")
