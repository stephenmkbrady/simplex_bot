#!/bin/bash

# SimpleX Bot Test Runner Script
# Runs tests inside Docker container to ensure consistent environment

set -e

echo "🧪 SimpleX Bot Test Runner"
echo "=========================="

# Check if Docker is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Function to run tests with different options
run_tests() {
    local test_type="$1"
    local extra_args="$2"
    
    echo "📋 Running $test_type tests..."
    docker-compose --profile testing run --rm simplex-bot-test-v2 python -m pytest $extra_args
}

# Parse command line arguments
case "${1:-all}" in
    "config")
        echo "🔧 Testing configuration management..."
        run_tests "configuration" "tests/test_config_manager.py tests/test_config_validation.py tests/test_environment_vars.py -v"
        ;;
    "integration")
        echo "🔗 Testing bot integration..."
        run_tests "integration" "tests/test_bot_integration.py -v"
        ;;
    "unit")
        echo "🧩 Testing individual units..."
        run_tests "unit" "tests/test_config_manager.py tests/test_config_validation.py tests/test_environment_vars.py -v"
        ;;
    "verbose")
        echo "📊 Running all tests with verbose output..."
        run_tests "all" "tests/ -v -s"
        ;;
    "coverage")
        echo "📈 Running tests with coverage report..."
        run_tests "coverage" "tests/ --cov=. --cov-report=term-missing --cov-report=html"
        ;;
    "quick")
        echo "⚡ Running quick tests only..."
        run_tests "quick" "tests/ -v -m 'not slow'"
        ;;
    "all"|"")
        echo "🎯 Running all tests..."
        run_tests "all" "tests/ -v"
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [test_type]"
        echo ""
        echo "Test types:"
        echo "  all         - Run all tests (default)"
        echo "  config      - Run configuration-related tests only"
        echo "  integration - Run integration tests only"
        echo "  unit        - Run unit tests only"
        echo "  verbose     - Run all tests with verbose output"
        echo "  coverage    - Run tests with coverage report"
        echo "  quick       - Run quick tests only (skip slow tests)"
        echo "  help        - Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                    # Run all tests"
        echo "  $0 config            # Test configuration only"
        echo "  $0 integration       # Test bot integration"
        echo "  $0 verbose           # Verbose output"
        exit 0
        ;;
    *)
        echo "❌ Unknown test type: $1"
        echo "Use '$0 help' to see available options"
        exit 1
        ;;
esac

echo ""
echo "✅ Test run completed!"
echo ""
echo "📊 Test Summary:"
echo "  - Configuration tests verify YAML parsing and env var substitution"
echo "  - Validation tests ensure config structure and required fields"
echo "  - Integration tests verify bot initialization with real config"
echo "  - Environment tests cover edge cases and error handling"
echo ""
echo "🚀 To run the bot with your configuration:"
echo "  docker-compose up -d"