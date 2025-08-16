FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

COPY app.py .
COPY wsgi.py .
COPY prompt.wav .
COPY assets/style.css assets/
COPY templates/index.html templates/
# Assuming you have requirements.txt; copy it too
COPY requirements.txt .

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5000 (common for Flask apps; adjust if your app uses a different port)
EXPOSE 5000

# Run the app
CMD ["gunicorn", "--workers 3", "--bind 0.0.0.0:5001", "wsgi:app"]
