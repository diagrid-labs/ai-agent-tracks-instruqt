import grpc
import uvicorn
from dapr.clients import DaprClient
from fastapi import FastAPI
from fastapi.responses import JSONResponse

SECRET_STORE = "secretstore"

app = FastAPI()


@app.get("/secret/{name}")
def get_secret(name: str):
    try:
        # The app only knows the secret store's name, never where the secrets really live.
        with DaprClient() as client:
            secret = client.get_secret(store_name=SECRET_STORE, key=name)
    except grpc.RpcError as e:
        # Show the failure instead of hiding it: a refusal by Dapr (for example by secret
        # scoping) is a 403 with the gRPC status name, anything else is a 500.
        code = e.code()
        status = 403 if code == grpc.StatusCode.PERMISSION_DENIED else 500
        return JSONResponse(status_code=status, content={"name": name, "error": code.name})
    if name not in secret.secret:
        return JSONResponse(status_code=500, content={"name": name, "error": "INTERNAL"})
    return {"name": name, "value": secret.secret[name]}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5001)
