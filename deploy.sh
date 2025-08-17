#!/bin/bash

# Weather Bot Deployment Script
# This script helps deploy the weather bot in various environments

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    if ! command_exists python3; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    python_version=$(python3 --version | cut -d' ' -f2)
    print_success "Python $python_version found"
    
    if ! command_exists git; then
        print_error "Git is required but not installed"
        exit 1
    fi
    
    print_success "Git found"
}

# Setup virtual environment
setup_venv() {
    print_status "Setting up virtual environment..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_success "Virtual environment created"
    else
        print_success "Virtual environment already exists"
    fi
    
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    print_success "Dependencies installed"
}

# Run health checks
run_health_checks() {
    print_status "Running health checks..."
    source venv/bin/activate
    
    if python3 health.py > /dev/null 2>&1; then
        print_success "Health checks passed"
    else
        print_warning "Health checks failed - check your configuration"
        python3 health.py
    fi
}

# Run tests
run_tests() {
    print_status "Running test suite..."
    source venv/bin/activate
    
    if pytest tests/ -q; then
        print_success "All tests passed"
    else
        print_error "Some tests failed"
        exit 1
    fi
}

# Setup configuration
setup_config() {
    print_status "Setting up configuration..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_warning "Created .env from example - please edit with your API keys"
        else
            print_error ".env file not found and no example available"
            exit 1
        fi
    else
        print_success "Configuration file exists"
    fi
    
    if [ ! -f "location.json" ]; then
        print_warning "location.json not found - using default Perth coordinates"
    fi
}

# Docker deployment
deploy_docker() {
    print_status "Building Docker image..."
    
    if ! command_exists docker; then
        print_error "Docker is required but not installed"
        exit 1
    fi
    
    docker build -t perthweatherbot:latest .
    print_success "Docker image built successfully"
    
    if [ -f "docker-compose.yml" ]; then
        print_status "Starting services with Docker Compose..."
        docker-compose up -d
        print_success "Services started. Access the app at http://localhost:8080"
    else
        print_status "Starting single container..."
        docker run -d --name perthweatherbot \
            --env-file .env \
            -v $(pwd)/weather_report.json:/app/weather_report.json \
            -v $(pwd)/forecast.mp3:/app/forecast.mp3 \
            perthweatherbot:latest
        print_success "Container started"
    fi
}

# Local development setup
setup_local() {
    print_status "Setting up local development environment..."
    
    check_prerequisites
    setup_config
    setup_venv
    run_tests
    run_health_checks
    
    print_success "Local setup completed!"
    print_status "To run the weather bot: source venv/bin/activate && python weatherbot.py"
}

# Production deployment
deploy_production() {
    print_status "Deploying to production..."
    
    check_prerequisites
    setup_config
    setup_venv
    run_tests
    run_health_checks
    
    print_status "Production deployment completed!"
    print_status "Set up a cron job to run: cd $(pwd) && source venv/bin/activate && python weatherbot.py"
}

# Show help
show_help() {
    echo "Weather Bot Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  local       Setup local development environment"
    echo "  production  Deploy for production use"
    echo "  docker      Build and run with Docker"
    echo "  test        Run test suite only"
    echo "  health      Run health checks only" 
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 local      # Setup for local development"
    echo "  $0 docker     # Deploy with Docker"
    echo "  $0 test       # Run tests"
}

# Main script logic
case "${1:-help}" in
    "local")
        setup_local
        ;;
    "production")
        deploy_production
        ;;
    "docker")
        check_prerequisites
        setup_config
        deploy_docker
        ;;
    "test")
        setup_venv
        run_tests
        ;;
    "health")
        setup_venv
        run_health_checks
        ;;
    "help"|*)
        show_help
        ;;
esac