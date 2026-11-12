import grpc
from dapr.clients import DaprClient
from fastapi import FastAPI
from fastapi.responses import JSONResponse

SECRET_STORE = "secretstore"

app = FastAPI()


# AppA and AppB have exactly the same code. Only the sidecar next to each of them is configured
# differently, and that decides which secrets each one may read. Even the port comes from
# dapr.yaml (uvicorn --port), not from the code.
@app.get("/secret/{name}")
def get_secret(name: str):
    try:
        with DaprClient() as client:
            secret = client.get_secret(store_name=SECRET_STORE, key=name)
    except grpc.RpcError as e:
        return failure(e, name)
    if name not in secret.secret:
        return JSONResponse(status_code=500, content={"name": name, "error": "INTERNAL"})
    return {"name": name, "value": secret.secret[name]}


def failure(e: grpc.RpcError, name: str):
    # Show the failure instead of hiding it: a refusal by Dapr (for example by secret
    # scoping) is a 403 with the gRPC status name, anything else is a 500.
    code = e.code()
    status = 403 if code == grpc.StatusCode.PERMISSION_DENIED else 500
    return JSONResponse(status_code=status, content={"name": name, "error": code.name})
