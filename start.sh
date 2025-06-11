#!/bin/bash
# Whisper Transcription App Startup Script

set -e  # Exit on any error

# Print header
echo "========================================"
echo "Whisper Transcription App Startup"
echo "========================================"

# Check for Docker CLI
if ! command -v docker &>/dev/null; then
    echo "❌ Error: Docker CLI is required but not found"
    echo "Please install Docker CLI and try again"
    exit 1
fi

# Check for Colima or Docker Desktop
DOCKER_RUNNING=false

# Check if Colima is installed and running
if command -v colima &>/dev/null; then
    COLIMA_STATUS=$(colima status 2>/dev/null | grep "Running" || echo "")
    if [[ -n "$COLIMA_STATUS" ]]; then
        DOCKER_RUNNING=true
        echo "✅ Colima is running"
    else
        echo "⚠️ Colima is installed but not running"
        echo "Starting Colima..."
        if [[ -f "colima-config.yaml" ]]; then
            echo "Colima config file found, but --config flag not supported in this version."
            echo "Using configuration parameters directly..."
            colima start --cpu 4 --memory 8 --disk 60 --mount-type virtiofs || { echo "❌ Failed to start Colima. Please start it manually with 'colima start'"; exit 1; }
        else
            echo "Using default Colima configuration with performance settings..."
            colima start --cpu 4 --memory 8 --disk 60 --mount-type virtiofs || { echo "❌ Failed to start Colima. Please start it manually with 'colima start'"; exit 1; }
        fi
        DOCKER_RUNNING=true
    fi
else
    # If Colima is not installed, check if Docker Desktop might be running
    if docker info &>/dev/null; then
        DOCKER_RUNNING=true
        echo "✅ Docker is running (possibly via Docker Desktop)"
    else
        echo "❌ Error: No running Docker environment detected"
        echo "Please install and start Colima with:"
        echo "  brew install colima docker"
        echo "  colima start"
        echo "Or start Docker Desktop if you prefer"
        exit 1
    fi
fi

# Check for Docker Compose
if ! (command -v docker-compose &>/dev/null || docker compose version &>/dev/null); then
    echo "❌ Error: Docker Compose is required but not found"
    echo "Please install Docker Compose and try again"
    exit 1
fi

echo "✅ Docker and Docker Compose are available"

# Create uploads directory if it doesn't exist
if [[ ! -d "uploads" ]]; then
    echo "Creating uploads directory..."
    mkdir -p uploads
fi

# Create input and output directories if they don't exist
if [[ ! -d "input" ]]; then
    echo "Creating input directory..."
    mkdir -p input
fi

if [[ ! -d "output" ]]; then
    echo "Creating output directory..."
    mkdir -p output
fi

# Function to run the cleanup process
run_cleanup() {
    # Run cleanup to remove unnecessary files
echo "========================================"
echo "Running system cleanup"
echo "========================================"

# Clean up Python cache files
echo "Cleaning up Python cache files..."
find . -name "*.pyc" -o -name "__pycache__" | xargs rm -rf 2>/dev/null || true

# Clean up temporary files
echo "Cleaning up temporary files..."
find . -type f -name "*.bak" -o -name "*.tmp" -o -name "*.swp" -o -name ".DS_Store" -o -name "._*" | xargs rm -f 2>/dev/null || true

# Clean up duplicate template files
echo "Cleaning up duplicate files..."
for file in "templates/index.html.new" "templates/index.html.fixed"; do
    if [[ -f "$file" ]]; then
        rm -f "$file"
        echo "Removed $file"
    fi
done

# Clean all files in uploads directory
echo "Cleaning up uploads directory..."
if [[ -d "uploads" && "$(ls -A uploads 2>/dev/null)" ]]; then
    find uploads -type f -exec rm -f {} \;
    echo "All files in uploads directory have been removed"
fi

# Run Python cleanup script if it exists (for more complex cleanup)
if [[ -f "cleanup.py" ]]; then
    echo "Running full cleanup script..."
    python3 cleanup.py --all
fi

echo "Cleanup completed!"
echo "========================================"
}

# Parse command line arguments
if [[ "$1" == "cleanup" ]]; then
    # Just run cleanup without starting the app
    run_cleanup
    exit 0
fi

# Run cleanup as part of normal startup
run_cleanup

# Check for .env file and create if it doesn't exist
if [[ ! -f ".env" ]]; then
    echo "Creating .env file..."
    cat > .env << EOL
# OpenAI API Key for transcription
OPENAI_API_KEY=

# BrightData Configuration
BRIGHTDATA_API_KEY=
BRIGHTDATA_DATASET_ID=

# Supabase Configuration
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=
EOL
    echo "⚠️ Please edit the .env file to add your API keys"
    echo ""
fi

# Start the application with Docker
echo "Starting application with Docker Compose..."
# Use the new docker compose syntax if available
if docker compose version &>/dev/null; then
    docker compose up -d
else
    docker-compose up -d
fi

echo ""
echo "✅ Whisper Transcription App is running!"
echo "Open http://localhost:9000 in your browser"
echo ""
echo "To view logs: docker compose logs -f (or docker-compose logs -f)"
echo "To stop: docker compose down (or docker-compose down)"
echo "To clean up files without starting: ./start.sh cleanup"

# Instruct the user on how to use the app without Python Virtual Environment
echo ""
echo "If you prefer to run without Docker, you can use:"
echo "1. Create a Python 3.11 virtual environment: python3 -m venv venv"
echo "2. Activate it: source venv/bin/activate"
echo "3. Install dependencies: pip install -r requirements.txt"
echo "4. Run the app: uvicorn app:app --reload"
echo "" 