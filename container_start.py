"""Use Render's assigned PORT, or 8000 for the existing local Docker scripts."""
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), workers=1)
