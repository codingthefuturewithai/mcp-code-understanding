#!/bin/bash

# MCP Code Understanding Server - Build Script for PyPI (UV-based)
#
# Usage:
#   ./scripts/build.sh                    # Run all tests, then build
#   ./scripts/build.sh --skip-tests       # Skip tests, build only
#   ./scripts/build.sh --quick-tests      # Run quick tests only (no integration)
#   ./scripts/build.sh --publish          # Build and publish without prompting

set -e  # Exit on error

# Parse command line arguments
SKIP_TESTS=false
QUICK_TESTS=false
AUTO_PUBLISH=false

for arg in "$@"; do
    case $arg in
        --skip-tests|-s)
            SKIP_TESTS=true
            shift
            ;;
        --quick-tests|-q)
            QUICK_TESTS=true
            shift
            ;;
        --publish|-p)
            AUTO_PUBLISH=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./scripts/build.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-tests, -s       Skip running tests before build"
            echo "  --quick-tests, -q      Run quick tests only (skip integration tests)"
            echo "  --publish, -p          Build and publish to PyPI without prompting"
            echo "  --help, -h             Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./scripts/build.sh                    # Full test suite + build"
            echo "  ./scripts/build.sh --quick-tests      # Quick tests + build"
            echo "  ./scripts/build.sh --skip-tests       # Build only, no tests"
            echo "  ./scripts/build.sh --publish          # Build + auto-publish to PyPI"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "🚀 Building MCP Code Understanding Server for PyPI..."
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ UV not found! Please install UV first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "✅ UV found: $(uv --version)"

# Get version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
echo "📦 Package version: ${VERSION}"
echo ""

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/
rm -rf dist/
rm -rf *.egg-info/
rm -rf src/*.egg-info/
echo "   ✓ Cleaned"
echo ""

# Run tests (unless skipped)
if [ "$SKIP_TESTS" = false ]; then
    if [ "$QUICK_TESTS" = true ]; then
        echo "🧪 Running quick tests (unit tests only)..."
        uv run pytest tests/ -v -m "not integration" || {
            echo "❌ Quick tests failed! Aborting build."
            exit 1
        }
        echo "   ✓ Quick tests passed"
    else
        echo "🧪 Running full test suite..."
        uv run pytest tests/ -v || {
            echo "❌ Tests failed! Aborting build."
            exit 1
        }
        echo "   ✓ All tests passed"
    fi
    echo ""
else
    echo "⏭️  Skipping tests (--skip-tests flag provided)"
    echo ""
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  Warning: You have uncommitted changes!"
    echo ""
    read -p "Continue with build anyway? (yes/no): " continue_response
    if [[ "$continue_response" != "yes" && "$continue_response" != "y" ]]; then
        echo "❌ Build cancelled. Please commit your changes first."
        exit 1
    fi
    echo ""
fi

# Ensure twine is available
echo "🔧 Ensuring build tools are available..."
uv pip install --quiet build twine
echo "   ✓ Build tools ready"
echo ""

# Build the package using UV
echo "🔨 Building package with UV..."
uv run python -m build
echo "   ✓ Package built"
echo ""

# Check the build
echo "✅ Checking build integrity..."
uv run python -m twine check dist/*
echo "   ✓ Build check passed"
echo ""

echo "📋 Build artifacts created:"
ls -lh dist/
echo ""

echo "🎉 Build complete!"
echo ""

# Upload to PyPI
if [ "$AUTO_PUBLISH" = true ]; then
    response="yes"
else
    read -p "Do you want to upload to PyPI now? (yes/no): " response
fi

if [[ "$response" == "yes" || "$response" == "y" ]]; then
    echo ""
    echo "📤 Uploading to PyPI..."
    uv run python -m twine upload dist/*

    if [ $? -eq 0 ]; then
        echo "✅ Successfully uploaded to PyPI!"
        echo ""

        # Offer to tag the release
        if [ "$AUTO_PUBLISH" = true ]; then
            tag_response="yes"
        else
            read -p "Do you want to tag this release as v${VERSION}? (yes/no): " tag_response
        fi

        if [[ "$tag_response" == "yes" || "$tag_response" == "y" ]]; then
            # Check if tag already exists
            if git rev-parse "v${VERSION}" >/dev/null 2>&1; then
                echo "⚠️  Tag v${VERSION} already exists. Skipping tag creation."
            else
                git tag "v${VERSION}"
                echo "✅ Tagged as v${VERSION}"
            fi

            # Check if we have a remote
            if git remote get-url origin &> /dev/null; then
                if [ "$AUTO_PUBLISH" = true ]; then
                    push_response="yes"
                else
                    read -p "Do you want to push commits and tags to GitHub? (yes/no): " push_response
                fi

                if [[ "$push_response" == "yes" || "$push_response" == "y" ]]; then
                    git push origin main
                    git push origin "v${VERSION}"
                    echo "✅ Commits and tag pushed to GitHub!"
                fi
            else
                echo "⚠️  No git remote configured. Skipping push."
            fi
        fi

        echo ""
        echo "🎊 Release v${VERSION} complete!"
        echo ""
        echo "📝 Next steps:"
        echo "  1. Verify on PyPI: https://pypi.org/project/code-understanding-mcp-server/${VERSION}/"
        echo "  2. Test installation: uvx code-understanding-mcp-server@${VERSION} --help"
        echo "  3. Update release notes on GitHub if needed"

    else
        echo "❌ Upload failed. Check your credentials and network connection."
        echo ""
        echo "Common issues:"
        echo "  - Missing PyPI credentials (configure ~/.pypirc)"
        echo "  - Network connectivity problems"
        echo "  - Version ${VERSION} already exists on PyPI"
        exit 1
    fi
else
    echo "⏭️  Skipping upload."
    echo ""
    echo "To upload later, run:"
    echo "  uv run python -m twine upload dist/*"
    echo ""
    echo "Or just run this script again:"
    echo "  ./scripts/build.sh"
fi

echo ""
echo "✨ All done!"
