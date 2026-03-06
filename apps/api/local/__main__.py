"""Run local API: python -m apps.api.local"""

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.api.local.app:app",
        host="0.0.0.0",
        port=int(__import__("os").environ.get("PORT", "8080")),
        reload=True,
    )
