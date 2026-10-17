"""Launch Wappler with python -m wappler.run."""

import os

import uvicorn


def main() -> None:
    """Run the ASGI server using PORT when provided by the hosting environment."""
    uvicorn.run("wappler.api:wappler_app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
