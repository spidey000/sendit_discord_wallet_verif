#!/bin/bash

# Docker Build Script with Auto-Versioning
# Builds the Sendit Discord Bot Docker image with automatic version increment

set -e

# Configuration
IMAGE_NAME="sendit-discord-bot"
IMAGES_DIR=".images"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DATE=$(date '+%Y%m%d_%H%M%S')

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%H:%M:%S')] ${message}${NC}"
}

# Function to print section headers
print_header() {
    echo
    echo -e "${PURPLE}================================${NC}"
    echo -e "${PURPLE} $1${NC}"
    echo -e "${PURPLE}================================${NC}"
}

# Function to detect next version
get_next_version() {
    local images_dir="$1"
    
    # Create images directory if it doesn't exist
    if [ ! -d "$images_dir" ]; then
        mkdir -p "$images_dir"
        print_status $YELLOW "Created $images_dir directory"
    fi
    
    # Find the latest version from existing .tar files
    local latest_version="0.0"
    
    # Look for version patterns in existing tar files
    if [ -d "$images_dir" ] && [ "$(ls -A $images_dir/*.tar.gz 2>/dev/null)" ]; then
        print_status $BLUE "Scanning for existing versions in $images_dir..."
        
        # Extract versions from filenames like: sendit-discord-bot_v1.5_20250121_143022.tar.gz
        for file in "$images_dir"/${IMAGE_NAME}_v*.tar.gz; do
            if [ -f "$file" ]; then
                # Extract version using regex (e.g., v1.5 -> 1.5)
                version=$(basename "$file" | sed -n 's/.*_v\([0-9]\+\.[0-9]\+\)_.*/\1/p')
                if [ -n "$version" ]; then
                    print_status $CYAN "Found existing version: v$version"
                    
                    # Compare versions (simple numeric comparison)
                    if (( $(echo "$version > $latest_version" | bc -l) )); then
                        latest_version=$version
                    fi
                fi
            fi
        done
    fi
    
    # Increment version
    if [ "$latest_version" = "0.0" ]; then
        next_version="1.0"
        print_status $GREEN "No existing versions found, starting with v$next_version"
    else
        # Increment minor version (e.g., 1.5 -> 1.6)
        major=$(echo $latest_version | cut -d. -f1)
        minor=$(echo $latest_version | cut -d. -f2)
        next_minor=$((minor + 1))
        next_version="$major.$next_minor"
        print_status $GREEN "Latest version: v$latest_version, next version: v$next_version"
    fi
    
    echo $next_version
}

# Function to validate environment
validate_environment() {
    print_header "Environment Validation"
    
    # Check if Docker is installed and running
    if ! command -v docker &> /dev/null; then
        print_status $RED "❌ Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_status $RED "❌ Docker is not running or not accessible"
        exit 1
    fi
    
    print_status $GREEN "✅ Docker is installed and running"
    
    # Check if Dockerfile exists
    if [ ! -f "Dockerfile" ]; then
        print_status $RED "❌ Dockerfile not found in current directory"
        exit 1
    fi
    
    print_status $GREEN "✅ Dockerfile found"
    
    # Check if bc is available for version comparison
    if ! command -v bc &> /dev/null; then
        print_status $YELLOW "⚠️  'bc' not found, installing basic calculator..."
        # Try to install bc if not available
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y bc
        elif command -v yum &> /dev/null; then
            sudo yum install -y bc
        elif command -v brew &> /dev/null; then
            brew install bc
        else
            print_status $YELLOW "⚠️  Could not install bc, using simple version comparison"
        fi
    fi
}

# Function to build Docker image
build_image() {
    local version=$1
    local build_date=$2
    
    print_header "Building Docker Image"
    
    # Build with multiple tags
    local image_latest="${IMAGE_NAME}:latest"
    local image_versioned="${IMAGE_NAME}:v${version}"
    local image_dated="${IMAGE_NAME}:v${version}_${build_date}"
    
    print_status $BLUE "Building image with tags:"
    print_status $BLUE "  - $image_latest"
    print_status $BLUE "  - $image_versioned"
    print_status $BLUE "  - $image_dated"
    
    # Build with build args for version info
    docker build \
        --build-arg BUILD_VERSION="v${version}" \
        --build-arg BUILD_DATE="$build_date" \
        --build-arg BUILD_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
        -t "$image_latest" \
        -t "$image_versioned" \
        -t "$image_dated" \
        .
    
    print_status $GREEN "✅ Docker image built successfully"
    
    # Display image info
    print_status $BLUE "Image information:"
    docker images | grep "$IMAGE_NAME" | head -3
}

# Function to save image to tar file
save_image() {
    local version=$1
    local build_date=$2
    local images_dir=$3
    
    print_header "Saving Docker Image"
    
    local image_tag="${IMAGE_NAME}:v${version}"
    local filename="${IMAGE_NAME}_v${version}_${build_date}.tar.gz"
    local filepath="${images_dir}/${filename}"
    
    print_status $BLUE "Saving image $image_tag to $filepath"
    
    # Create a temporary file for the uncompressed tar
    local temp_tar="${filepath%.gz}"
    
    # Save image to tar file
    docker save "$image_tag" -o "$temp_tar"
    
    print_status $BLUE "Compressing image archive..."
    gzip "$temp_tar"
    
    # Get file size
    local file_size=$(ls -lh "$filepath" | awk '{print $5}')
    print_status $GREEN "✅ Image saved to: $filepath"
    print_status $GREEN "📦 Archive size: $file_size"
    
    # Create a symlink to latest
    local latest_link="${images_dir}/${IMAGE_NAME}_latest.tar.gz"
    if [ -L "$latest_link" ]; then
        rm "$latest_link"
    fi
    ln -s "$(basename "$filepath")" "$latest_link"
    print_status $GREEN "🔗 Created symlink: $latest_link -> $(basename "$filepath")"
}

# Function to cleanup old images (optional)
cleanup_old_images() {
    local images_dir=$1
    local keep_count=${2:-5}  # Keep last 5 images by default
    
    print_header "Cleanup Old Images"
    
    print_status $BLUE "Cleaning up old image archives (keeping last $keep_count)..."
    
    # Count existing archives
    local archive_count=$(ls -1 "$images_dir"/${IMAGE_NAME}_v*.tar.gz 2>/dev/null | wc -l)
    
    if [ "$archive_count" -gt "$keep_count" ]; then
        local to_remove=$((archive_count - keep_count))
        print_status $YELLOW "Found $archive_count archives, removing $to_remove oldest..."
        
        # Remove oldest archives
        ls -t "$images_dir"/${IMAGE_NAME}_v*.tar.gz | tail -n +$((keep_count + 1)) | xargs rm -f
        
        print_status $GREEN "✅ Cleanup completed"
    else
        print_status $GREEN "✅ No cleanup needed ($archive_count archives, keeping $keep_count)"
    fi
}

# Function to display build summary
display_summary() {
    local version=$1
    local build_date=$2
    local images_dir=$3
    
    print_header "Build Summary"
    
    local filepath="${images_dir}/${IMAGE_NAME}_v${version}_${build_date}.tar.gz"
    local file_size=$(ls -lh "$filepath" | awk '{print $5}')
    
    echo -e "${GREEN}🎉 Build completed successfully!${NC}"
    echo
    echo -e "${CYAN}📋 Build Details:${NC}"
    echo -e "   ${BLUE}Version:${NC}     v${version}"
    echo -e "   ${BLUE}Build Date:${NC}  ${build_date}"
    echo -e "   ${BLUE}Image Name:${NC}  ${IMAGE_NAME}"
    echo -e "   ${BLUE}Archive:${NC}     ${filepath}"
    echo -e "   ${BLUE}Size:${NC}        ${file_size}"
    echo
    echo -e "${CYAN}🐳 Docker Images:${NC}"
    docker images | grep "$IMAGE_NAME" | head -5
    echo
    echo -e "${CYAN}📁 Available Archives:${NC}"
    ls -lh "$images_dir"/${IMAGE_NAME}_v*.tar.gz 2>/dev/null | tail -5 || echo "   No archives found"
    echo
    echo -e "${GREEN}🚀 Ready for deployment!${NC}"
    echo -e "   ${BLUE}Deploy command:${NC} Load the .tar.gz file into Portainer"
    echo -e "   ${BLUE}Local test:${NC}     docker run --rm -p 8080:8080 ${IMAGE_NAME}:v${version}"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help           Show this help message"
    echo "  -v, --version VER    Override version (e.g., 2.1)"
    echo "  -c, --cleanup NUM    Number of old images to keep (default: 5)"
    echo "  --no-cleanup         Skip cleanup of old images"
    echo "  --no-compress        Save as .tar instead of .tar.gz"
    echo "  --list-images        List existing image archives and exit"
    echo
    echo "Examples:"
    echo "  $0                   Build with auto-incremented version"
    echo "  $0 -v 2.0           Build with specific version 2.0"
    echo "  $0 -c 10            Build and keep 10 old images"
    echo "  $0 --list-images    Show existing archives"
}

# Function to list existing images
list_images() {
    local images_dir="$1"
    
    print_header "Existing Image Archives"
    
    if [ -d "$images_dir" ] && [ "$(ls -A $images_dir/*.tar.gz 2>/dev/null)" ]; then
        echo -e "${CYAN}📁 Archives in $images_dir:${NC}"
        ls -lht "$images_dir"/${IMAGE_NAME}_v*.tar.gz 2>/dev/null | while read line; do
            echo -e "   ${BLUE}$line${NC}"
        done
        
        echo
        echo -e "${CYAN}🔗 Symlinks:${NC}"
        ls -la "$images_dir"/${IMAGE_NAME}_latest.tar.gz 2>/dev/null | while read line; do
            echo -e "   ${BLUE}$line${NC}"
        done
    else
        echo -e "${YELLOW}No existing archives found in $images_dir${NC}"
    fi
}

# Main function
main() {
    local version_override=""
    local cleanup_count=5
    local do_cleanup=true
    local compress=true
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -v|--version)
                version_override="$2"
                shift 2
                ;;
            -c|--cleanup)
                cleanup_count="$2"
                shift 2
                ;;
            --no-cleanup)
                do_cleanup=false
                shift
                ;;
            --no-compress)
                compress=false
                shift
                ;;
            --list-images)
                list_images "$IMAGES_DIR"
                exit 0
                ;;
            *)
                print_status $RED "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Change to script directory
    cd "$SCRIPT_DIR"
    
    print_header "Sendit Discord Bot - Docker Build Script"
    
    # Validate environment
    validate_environment
    
    # Determine version
    if [ -n "$version_override" ]; then
        version="$version_override"
        print_status $YELLOW "Using override version: v$version"
    else
        version=$(get_next_version "$IMAGES_DIR")
    fi
    
    # Build image
    build_image "$version" "$BUILD_DATE"
    
    # Save image
    save_image "$version" "$BUILD_DATE" "$IMAGES_DIR"
    
    # Cleanup old images
    if [ "$do_cleanup" = true ]; then
        cleanup_old_images "$IMAGES_DIR" "$cleanup_count"
    fi
    
    # Display summary
    display_summary "$version" "$BUILD_DATE" "$IMAGES_DIR"
}

# Handle Ctrl+C gracefully
trap 'print_status $RED "❌ Build interrupted by user"; exit 1' INT

# Run main function
main "$@"