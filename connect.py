# Create an API client and prove we are connected to the OpenAlgo server.
import os

from openalgo import api

# Best practice: read the key from an environment variable instead of hard-coding it.
client = api(
    api_key=os.getenv("OPENALGO_API_KEY", "a517d30ed416f01feb161c824d399e2c23d093a6d2b13e4684d643201189426e"),
    host=os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000"),
)

status = client.analyzerstatus()  # a tiny call that confirms the connection works
print("Connected:", status["status"] == "success")
print("Current mode:", status["data"]["mode"])