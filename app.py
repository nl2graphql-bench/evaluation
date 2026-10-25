
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import shutil
from pathlib import Path
from evalExec import evaluate_graphql_accuracy

app = FastAPI(title="GraphQL Accuracy API")

UPLOAD_DIR = Path("uploaded_files")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = Path("api_output")
OUTPUT_DIR.mkdir(exist_ok=True)

@app.get("/")
async def root():
    return {"message": "GraphQL Accuracy API is running. Use /evaluate/ to POST CSV files."}

@app.post("/evaluate/")
async def evaluate_upload(file: UploadFile = File(...)):
    """
    Upload a CSV file and return GraphQL accuracy metrics as JSON.
    """

    input_path = UPLOAD_DIR / file.filename
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        metrics = evaluate_graphql_accuracy(str(input_path))
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return JSONResponse(content=metrics)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
