import uvicorn
from dapr.clients import DaprClient
from fastapi import FastAPI

SECRET_STORE = "secretstore"

app = FastAPI()


@app.get("/secret/{name}")
def get_secret(name: str):
    # The app only knows the secret store's name, never where the secrets really live.
    with DaprClient() as client:
        secret = client.get_secret(store_name=SECRET_STORE, key=name)
    return {"name": name, "value": secret.secret[name]}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5001)
