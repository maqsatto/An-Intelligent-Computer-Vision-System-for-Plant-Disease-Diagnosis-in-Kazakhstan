from fastapi import Request


def session(request: Request):
    with request.app.state.sessions() as db:
        yield db
