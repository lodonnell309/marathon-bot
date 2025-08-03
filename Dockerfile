# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install gunicorn and uvicorn explicitly
RUN pip install gunicorn uvicorn

# Copy the rest of the application code into the container
COPY . .

# Use the PORT environment variable provided by Cloud Run.
# The default of 8080 is used if the variable is not set (e.g., for local testing).
# The `app:app` syntax assumes your FastAPI app instance is named `app`
# in a file named `app.py`.
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app:app", "--bind", "0.0.0.0:${PORT:-8080}"]
