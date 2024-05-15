import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_SID = os.getenv("TWILIO_SID")
ENVIRONMENT = os.getenv("ENVIRONMENT")
