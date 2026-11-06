import io
import logging
from pathlib import Path
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src import (
    MovieStorage,
    MovieUploadInfo,
    MovieDataResponse,
    MovieProcessingReport,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Processing API", version="1.0.0")
app.middleware("http")(log_requests)
storage = MovieStorage()

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return HealthResponse(status="ok", version=app.version)

@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a movie CSV and replace the stored collection."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".csv":
        logger.warning(f"Unsupported file format: {suffix}")
        raise HTTPException(status_code=400, detail=f"Unsupported file format: '{suffix}'. Please upload a .csv file.")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        logger.warning(f"Could not parse CSV: filename={file.filename}, error={e}")
        raise HTTPException(status_code=400, detail=f"Could not read '{file.filename}' as a CSV file: {e}")

    # Same columns in any order are fine; extra or missing columns are not
    if sorted(df.columns) != sorted(MOVIE_COLUMNS):
        logger.warning(f"Unexpected columns: filename={file.filename}, columns={list(df.columns)}")
        raise HTTPException(status_code=400, detail=f"CSV must have exactly these columns: {MOVIE_COLUMNS}")
    if df.empty:
        logger.warning(f"CSV has no data rows: filename={file.filename}")
        raise HTTPException(status_code=400, detail=f"'{file.filename}' has no data rows")
    df = df[MOVIE_COLUMNS]

    storage.save(df)
    logger.info(f"Uploaded movies: filename={file.filename}, rows={len(df)}")
    return MovieUploadInfo(
        filename=file.filename,
        rows=len(df),
        columns=len(df.columns),
        column_names=list(df.columns),
    )

@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return up to limit stored movies and the total count."""
    records = storage.select_columns(MOVIE_COLUMNS, limit=limit)
    total_rows = storage.count_movies()
    logger.info(f"Retrieved movies: returned_rows={len(records)}, total_rows={total_rows}")
    return {"data": records, "total_rows": total_rows}

@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1)
):
    """Return id plus the selected fields for movies at or above min_rating."""
    try:
        records = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        logger.warning(f"Search failed: columns={columns}, error={error}")
        raise HTTPException(status_code=400, detail=str(error))

    logger.info(f"Queried movies: columns={columns}, min_rating={min_rating}, returned_rows={len(records)}")
    return records

@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate and process the stored movies using MP1 functions."""
    df = storage.get()
    if df.empty:
        logger.warning("No movies to process")
        raise HTTPException(status_code=400, detail="No movies stored. Upload a CSV first.")

    config_dict = config.model_dump()
    required_columns = config_dict["validation"]["required_columns"]
    numeric_columns = config_dict["validation"]["numeric_columns"]

    missing = [col for col in numeric_columns if col not in df.columns]
    if missing:
        logger.warning(f"Numeric column(s) not found: columns={missing}")
        raise HTTPException(status_code=400, detail=f"Numeric column(s) not found: {missing}")

    try:
        validated = validate_dataframe(df, required_columns, numeric_columns)
        validation_removed = len(df) - len(validated)
        logger.info(f"Validated movies: rows={len(df)} → {len(validated)}")
        validated_copy = validated.copy()
        processed = process_data(validated, config_dict)
    except ValueError as error:
        logger.warning(f"Processing failed: error={error}")
        raise HTTPException(status_code=400, detail=str(error))

    report = create_cleaning_report(validated_copy, processed)
    storage.save(processed)
    logger.info(
        f"Processed movies: validation_removed={validation_removed}, "
        f"rows_before={report['rows_before']}, rows_after={report['rows_after']}"
    )
    return {
        "validation_rows_removed": validation_removed,
        "cleaning_report": report,
    }
