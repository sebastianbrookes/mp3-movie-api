# MP3 Movie API

This project is a FastAPI application that stores one movie collection in SQLite, cleans it with the MP1 data pipeline, and caches repeated retrievals. `main.py` defines the endpoints, while the `src/` package holds the Pydantic models (`models.py`), database setup (`database.py`), SQL storage (`storage.py`), the movie cache (`cache.py`), request-logging middleware, and logging setup. `POST /upload` checks that a CSV has exactly the `title`, `release_year`, `rating`, and `genre` columns and at least one row, then `MovieStorage` replaces the stored rows in `data/movies.db` in a single transaction. `GET /movies` and `GET /movies/search` read from SQLite using SQL for selecting, filtering, sorting, limiting, and counting. `POST /movies/process` loads the stored movies into a DataFrame, validates and cleans them with the `data_pipeline` functions, and saves the result back to SQLite. Responses from `GET /movies` are cached in FakeRedis for 90 seconds under one key per `limit`, so a repeated request skips the database. After every successful upload or processing step, the whole cache is cleared so later retrievals never return outdated rows. Because the movies live in SQLite rather than in memory, they survive server restarts, while the cache starts empty each time.

## Commands

Start the API from the repository root:

```bash
python -m uvicorn main:app --reload
```

Run the tests:

```bash
python -m pytest tests -v
```

## Sample Processing Request

After uploading `fixtures/sample_movies.csv`, send this body to `POST /movies/process`:

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {
      "enabled": true,
      "columns": ["rating"],
      "method": "iqr",
      "threshold": 1.5
    }
  }
}
```

Expected result:

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```

Two duplicate rows (Movie B and Movie D) and two low-rating outliers (Movie Q and Movie R) are removed, leaving 16 movies.
